from logging import getLogger
from os import path as ospath, listdir
import shutil
from contextlib import suppress
from re import search as re_search
from secrets import token_hex

from yt_dlp import YoutubeDL, DownloadError

from .... import task_dict_lock, task_dict
from ....core.config_manager import BinConfig
from ...ext_utils.bot_utils import sync_to_async, async_to_sync
from ...ext_utils.task_manager import (
    check_running_tasks,
    stop_duplicate_check,
    limit_checker,
)
from ...mirror_leech_utils.status_utils.queue_status import QueueStatus
from ...telegram_helper.message_utils import send_status_message
from ..status_utils.yt_dlp_status import YtDlpStatus


LOGGER = getLogger(__name__)


def get_cookie_file(user_dict, user_id=None):
    """
    Find the YouTube cookie file.

    Supported:
        cookie.txt
        cookies.txt
        cookies/cookie.txt
        cookies/cookies.txt
        cookies/<user_id>/cookie.txt
        cookies/<user_id>/cookies.txt

    USER_COOKIE_FILE has highest priority when configured.
    """

    user_dict = user_dict or {}

    use_default = user_dict.get("USE_DEFAULT_COOKIE", False)

    cookie_names = (
        "cookie.txt",
        "cookies.txt",
    )

    # Explicit user-configured cookie
    user_cookie = user_dict.get("USER_COOKIE_FILE", "")
    if user_cookie:
        if ospath.isfile(user_cookie):
            return user_cookie, None

        LOGGER.warning(
            "Configured USER_COOKIE_FILE does not exist: %s",
            user_cookie,
        )

    # User-specific cookie
    if user_id:
        user_cookie_dir = ospath.join("cookies", str(user_id))

        for filename in cookie_names:
            cookie_path = ospath.join(user_cookie_dir, filename)

            if ospath.isfile(cookie_path):
                return cookie_path, None

    # Default cookies
    if use_default:
        search_paths = []

        for filename in cookie_names:
            search_paths.append(filename)

        for filename in cookie_names:
            search_paths.append(ospath.join("cookies", filename))

        for cookie_path in search_paths:
            if ospath.isfile(cookie_path):
                return cookie_path, None

        return None, None

    # Fallback to global cookie
    search_paths = []

    for filename in cookie_names:
        search_paths.append(filename)

    for filename in cookie_names:
        search_paths.append(ospath.join("cookies", filename))

    for cookie_path in search_paths:
        if ospath.isfile(cookie_path):
            return cookie_path, None

    return None, None


class MyLogger:
    def __init__(self, obj, listener):
        self._obj = obj
        self._listener = listener

    def debug(self, msg):
        # Detect filename changes caused by merge/extract operations.
        if not self._obj.is_playlist:
            if match := (
                re_search(r".Merger..Merging formats into..(.*?).$", msg)
                or re_search(r".ExtractAudio..Destination..(.*?)$", msg)
            ):
                LOGGER.info(msg)

                newname = match.group(1)
                newname = newname.rsplit("/", 1)[-1]

                self._listener.name = newname

    @staticmethod
    def warning(msg):
        LOGGER.warning(msg)

    @staticmethod
    def error(msg):
        if msg != "ERROR: Cancelling...":
            LOGGER.error(msg)


def find_node_executable():
    return (
        shutil.which("node")
        or shutil.which(
            "node",
            path="/usr/local/bin:/usr/bin:/bin",
        )
    )


class YoutubeDLHelper:
    def __init__(self, listener):
        self._last_downloaded = 0
        self._progress = 0
        self._downloaded_bytes = 0
        self._download_speed = 0
        self._eta = "-"

        self._listener = listener
        self._gid = ""
        self._ext = ""

        self.is_playlist = False
        self.keep_thumb = False
        self.playlist_count = 0

        node_path = find_node_executable()

        ffmpeg_bin = f"/bin/{BinConfig.FFMPEG_NAME}"

        if not ospath.exists(ffmpeg_bin):
            ffmpeg_bin = (
                shutil.which(BinConfig.FFMPEG_NAME)
                or shutil.which("ffmpeg")
                or ffmpeg_bin
            )

        self.opts = {
            "progress_hooks": [
                self._on_download_progress,
            ],

            "logger": MyLogger(
                self,
                self._listener,
            ),

            "usenetrc": True,

            "allow_multiple_video_streams": True,
            "allow_multiple_audio_streams": True,

            "noprogress": True,
            "allow_playlist_files": True,
            "overwrites": True,

            "trim_file_name": 220,

            "ffmpeg_location": ffmpeg_bin,

            "fragment_retries": 10,
            "retries": 10,

            "retry_sleep_functions": {
                "http": lambda n: 3,
                "fragment": lambda n: 3,
                "file_access": lambda n: 3,
                "extractor": lambda n: 3,
            },

            # Do not force mweb/ios/web here.
            #
            # Start with the clients that generally work best with
            # normal browser cookies.
            "extractor_args": {
                "youtube": {
                    "player_client": [
                        "default",
                        "web_embedded",
                    ],
                },
            },
        }

        if node_path:
            self.opts["js_runtimes"] = {
                "node": {
                    "path": node_path,
                }
            }

            LOGGER.info(
                "yt-dlp JavaScript runtime: node=%s",
                node_path,
            )
        else:
            LOGGER.warning(
                "Node.js was not found. "
                "Some YouTube extraction features may fail."
            )

        cookie_to_use, _ = get_cookie_file(
            self._listener.user_dict,
            self._listener.user_id,
        )

        if cookie_to_use and ospath.isfile(cookie_to_use):
            self.opts["cookiefile"] = cookie_to_use

            LOGGER.info(
                "YouTube cookies enabled: %s | User ID: %s",
                cookie_to_use,
                self._listener.user_id,
            )
        else:
            LOGGER.warning(
                "No YouTube cookie file found | User ID: %s",
                self._listener.user_id,
            )

    @property
    def download_speed(self):
        return self._download_speed

    @property
    def downloaded_bytes(self):
        return self._downloaded_bytes

    @property
    def size(self):
        return self._listener.size

    @property
    def progress(self):
        return self._progress

    @property
    def eta(self):
        return self._eta

    def _on_download_progress(self, d):
        if self._listener.is_cancelled:
            raise ValueError("Cancelling...")

        status = d.get("status")

        if status == "finished":
            if self.is_playlist:
                self._last_downloaded = 0

        elif status == "downloading":
            self._download_speed = d.get("speed") or 0

            if self.is_playlist:
                downloaded_bytes = (
                    d.get("downloaded_bytes") or 0
                )

                chunk_size = (
                    downloaded_bytes - self._last_downloaded
                )

                self._last_downloaded = downloaded_bytes
                self._downloaded_bytes += chunk_size

            else:
                if d.get("total_bytes"):
                    self._listener.size = (
                        d.get("total_bytes") or 0
                    )

                elif d.get("total_bytes_estimate"):
                    self._listener.size = (
                        d.get("total_bytes_estimate") or 0
                    )

                self._downloaded_bytes = (
                    d.get("downloaded_bytes") or 0
                )

                self._eta = d.get("eta", "-") or "-"

            try:
                if self._listener.size:
                    self._progress = (
                        self._downloaded_bytes
                        / self._listener.size
                    ) * 100

            except ZeroDivisionError:
                pass

    async def _on_download_start(self, from_queue=False):
        async with task_dict_lock:
            task_dict[self._listener.mid] = YtDlpStatus(
                self._listener,
                self,
                self._gid,
            )

        if not from_queue:
            await self._listener.on_download_start()

            if (
                self._listener.multi <= 1
                and not self._listener.is_rss
            ):
                await send_status_message(
                    self._listener.message
                )

    def _on_download_error(self, error):
        async_to_sync(
            self._listener.on_download_error,
            error,
        )

    def _get_client_fallbacks(self):
        """
        Controlled YouTube client fallback order.

        Avoids repeatedly trying clients that commonly require
        PO Tokens or have additional restrictions.
        """

        return [
            [
                "default",
                "web_embedded",
            ],
            [
                "web_embedded",
            ],
            [
                "default",
            ],
        ]

    def _make_client_options(self, clients):
        curr_opts = self.opts.copy()

        extractor_args = dict(
            curr_opts.get(
                "extractor_args",
                {},
            )
        )

        youtube_args = dict(
            extractor_args.get(
                "youtube",
                {},
            )
        )

        youtube_args["player_client"] = clients

        extractor_args["youtube"] = youtube_args

        curr_opts["extractor_args"] = extractor_args

        return curr_opts

    def _extract_meta_data(self):
        opts = self.opts.copy()

        if self.is_playlist:
            opts["extract_flat"] = "in_playlist"
            opts["ignoreerrors"] = True

        result = None
        last_exc = None

        for clients in self._get_client_fallbacks():
            try:
                curr_opts = self._make_client_options(
                    clients
                )

                LOGGER.info(
                    "Extracting YouTube metadata using clients: %s",
                    ", ".join(clients),
                )

                with YoutubeDL(curr_opts) as ydl:
                    result = ydl.extract_info(
                        self._listener.link,
                        download=False,
                    )

                if result is not None:
                    break

            except Exception as e:
                last_exc = e

                LOGGER.warning(
                    "YouTube metadata extraction failed "
                    "with clients %s: %s",
                    clients,
                    e,
                )

        if result is None:
            err_msg = (
                str(last_exc)
                if last_exc
                else "YouTube extraction returned no information."
            )

            self._on_download_error(err_msg)
            return

        if self.is_playlist:
            entries = list(
                result.get("entries", [])
            )

            self.playlist_count = (
                result.get("playlist_count")
                or len(
                    [
                        entry
                        for entry in entries
                        if entry
                    ]
                )
            )

        if "entries" in result:
            entries = [
                entry
                for entry in result["entries"]
                if entry
            ]

            for entry in entries:
                if entry.get("ext") == "unknown_video":
                    entry["ext"] = "mp4"

                if "filesize_approx" in entry:
                    self._listener.size += (
                        entry.get(
                            "filesize_approx",
                            0,
                        )
                        or 0
                    )

                elif "filesize" in entry:
                    self._listener.size += (
                        entry.get(
                            "filesize",
                            0,
                        )
                        or 0
                    )

            if not self._listener.name:
                playlist_title = (
                    result.get("title")
                    or result.get("playlist_title")
                )

                if playlist_title:
                    self._listener.name = playlist_title

                elif entries:
                    outtmpl_ = (
                        "%(series,playlist_title,channel)s"
                        "%(season_number& |)s"
                        "%(season_number&S|)s"
                        "%(season_number|)02d."
                        "%(ext)s"
                    )

                    with suppress(Exception):
                        with YoutubeDL(opts) as ydl:
                            filename = ydl.prepare_filename(
                                entries[0],
                                outtmpl=outtmpl_,
                            )

                            if filename:
                                self._listener.name = (
                                    ospath.splitext(
                                        filename
                                    )[0]
                                )

                if not self._listener.name:
                    self._listener.name = "Playlist"

        else:
            if result.get("ext") == "unknown_video":
                result["ext"] = "mp4"

            outtmpl_ = (
                "%(title,fulltitle,alt_title)s"
                "%(season_number& |)s"
                "%(season_number&S|)s"
                "%(season_number|)02d"
                "%(episode_number&E|)s"
                "%(episode_number|)02d"
                "%(height& |)s"
                "%(height|)s"
                "%(height&p|)s"
                "%(fps|)s"
                "%(fps&fps|)s"
                "%(tbr& |)s"
                "%(tbr|)d."
                "%(ext)s"
            )

            with YoutubeDL(opts) as ydl:
                real_name = ydl.prepare_filename(
                    result,
                    outtmpl=outtmpl_,
                )

            ext = ospath.splitext(real_name)[-1]

            self._listener.name = (
                f"{self._listener.name}{ext}"
                if self._listener.name
                else real_name
            )

            if not self._ext:
                self._ext = ext

    def _download(self, download_path):
        client_fallbacks = self._get_client_fallbacks()

        last_err = None

        for clients in client_fallbacks:
            if self._listener.is_cancelled:
                return

            curr_opts = self._make_client_options(
                clients
            )

            try:
                LOGGER.info(
                    "Starting YouTube download using clients: %s",
                    ", ".join(clients),
                )

                with YoutubeDL(curr_opts) as ydl:
                    ydl.download(
                        [
                            self._listener.link
                        ]
                    )

                # Download completed.
                if self.is_playlist and (
                    not ospath.exists(download_path)
                    or len(listdir(download_path)) == 0
                ):
                    last_err = (
                        "No video available to download "
                        "from this playlist."
                    )
                    continue

                if self._listener.is_cancelled:
                    return

                async_to_sync(
                    self._listener.on_download_complete
                )

                return

            except DownloadError as e:
                last_err = e

                LOGGER.warning(
                    "YouTube download failed with clients "
                    "%s: %s",
                    clients,
                    e,
                )

                if self._listener.is_cancelled:
                    return

            except Exception as e:
                last_err = e

                LOGGER.warning(
                    "Unexpected YouTube download error "
                    "with clients %s: %s",
                    clients,
                    e,
                )

                if self._listener.is_cancelled:
                    return

        if not self._listener.is_cancelled:
            LOGGER.error(
                "YT-DLP Download Failed | URL: %s | "
                "Format: %s | Error: %s",
                self._listener.link,
                self.opts.get("format"),
                last_err,
            )

            self._on_download_error(
                str(last_err)
                if last_err
                else "YouTube download failed."
            )

    async def add_download(
        self,
        path,
        qual,
        playlist,
        options,
    ):
        cookie_to_use, err = get_cookie_file(
            self._listener.user_dict,
            self._listener.user_id,
        )

        if err and not cookie_to_use:
            await self._listener.on_download_error(err)
            return

        if cookie_to_use and ospath.isfile(cookie_to_use):
            self.opts["cookiefile"] = cookie_to_use

        if playlist:
            self.opts["ignoreerrors"] = True
            self.is_playlist = True

        self._gid = token_hex(5)

        await self._on_download_start()

        self.opts["postprocessors"] = [
            {
                "add_chapters": True,
                "add_infojson": "if_exists",
                "add_metadata": True,
                "key": "FFmpegMetadata",
            }
        ]

        if qual.startswith("ba/b-"):
            audio_info = qual.split("-")

            qual = audio_info[0]
            audio_format = audio_info[1]
            rate = audio_info[2]

            self.opts["postprocessors"].append(
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": audio_format,
                    "preferredquality": rate,
                }
            )

            if audio_format == "vorbis":
                self._ext = ".ogg"

            elif audio_format == "alac":
                self._ext = ".m4a"

            else:
                self._ext = f".{audio_format}"

        if (
            not self._listener.is_leech
            or self._listener.thumbnail_layout
        ):
            self.opts["writethumbnail"] = False

        if options:
            self._set_options(options)

        # IMPORTANT:
        # Preserve the quality selected by the bot.
        self.opts["format"] = qual

        await sync_to_async(
            self._extract_meta_data
        )

        if self._listener.is_cancelled:
            return

        base_name, ext = ospath.splitext(
            self._listener.name
        )

        trim_name = (
            self._listener.name
            if self.is_playlist
            else base_name
        )

        if len(trim_name.encode()) > 200:
            self._listener.name = (
                self._listener.name[:200]
                if self.is_playlist
                else f"{base_name[:200]}{ext}"
            )

            base_name = ospath.splitext(
                self._listener.name
            )[0]

        start_path = (
            path
            if self.keep_thumb
            else f"{path}/yt-dlp-thumb"
        )

        if self.is_playlist:
            self.opts["outtmpl"] = {
                "default": (
                    f"{path}/{self._listener.name}/"
                    "%(title,fulltitle,alt_title)s"
                    "%(season_number& |)s"
                    "%(season_number&S|)s"
                    "%(season_number|)02d"
                    "%(episode_number&E|)s"
                    "%(episode_number|)02d"
                    "%(height& |)s"
                    "%(height|)s"
                    "%(height&p|)s"
                    "%(fps|)s"
                    "%(fps&fps|)s"
                    "%(tbr& |)s"
                    "%(tbr|)d.%(ext)s"
                ),
                "thumbnail": (
                    f"{start_path}/"
                    "%(title,fulltitle,alt_title)s"
                    "%(season_number& |)s"
                    "%(season_number&S|)s"
                    "%(season_number|)02d"
                    "%(episode_number&E|)s"
                    "%(episode_number|)02d"
                    "%(height& |)s"
                    "%(height|)s"
                    "%(height&p|)s"
                    "%(fps|)s"
                    "%(fps&fps|)s"
                    "%(tbr& |)s"
                    "%(tbr|)d.%(ext)s"
                ),
            }

        elif "download_ranges" in options:
            self.opts["outtmpl"] = {
                "default": (
                    f"{path}/{base_name}/"
                    "%(section_number|)s"
                    "%(section_number&.|)s"
                    "%(section_title|)s"
                    "%(section_title&-|)s"
                    "%(title,fulltitle,alt_title)s "
                    "%(section_start)s to "
                    "%(section_end)s.%(ext)s"
                ),
                "thumbnail": (
                    f"{start_path}/"
                    "%(section_number|)s"
                    "%(section_number&.|)s"
                    "%(section_title|)s"
                    "%(section_title&-|)s"
                    "%(title,fulltitle,alt_title)s "
                    "%(section_start)s to "
                    "%(section_end)s.%(ext)s"
                ),
            }

        elif any(
            key in options
            for key in [
                "writedescription",
                "writeinfojson",
                "writeannotations",
                "writedesktoplink",
                "writewebloclink",
                "writelink",
                "writeurllink",
                "writesubtitles",
                "write_all_thumbnails",
            ]
        ):
            self.opts["outtmpl"] = {
                "default": (
                    f"{path}/{base_name}/"
                    f"{self._listener.name}"
                ),
                "thumbnail": (
                    f"{start_path}/"
                    f"{base_name}.%(ext)s"
                ),
            }

        else:
            self.opts["outtmpl"] = {
                "default": (
                    f"{path}/"
                    f"{self._listener.name}"
                ),
                "thumbnail": (
                    f"{start_path}/"
                    f"{base_name}.%(ext)s"
                ),
            }

        if qual.startswith("ba/b"):
            self._listener.name = (
                f"{base_name}{self._ext}"
            )

        if self.opts["writethumbnail"]:
            self.opts["postprocessors"].append(
                {
                    "format": "jpg",
                    "key": "FFmpegThumbnailsConvertor",
                    "when": "before_dl",
                }
            )

        if self._ext in [
            ".mp3",
            ".mkv",
            ".mka",
            ".ogg",
            ".opus",
            ".flac",
            ".m4a",
            ".mp4",
            ".mov",
            ".m4v",
        ]:
            self.opts["postprocessors"].append(
                {
                    "already_have_thumbnail": (
                        self.opts["writethumbnail"]
                    ),
                    "key": "EmbedThumbnail",
                }
            )

        msg, button = await stop_duplicate_check(
            self._listener
        )

        if msg:
            await self._listener.on_download_error(
                msg,
                button,
            )
            return

        limit_exceeded = await limit_checker(
            self._listener,
            self.playlist_count,
        )

        if limit_exceeded:
            await self._listener.on_download_error(
                limit_exceeded,
                is_limit=True,
            )
            return

        add_to_queue, event = await check_running_tasks(
            self._listener
        )

        if add_to_queue:
            LOGGER.info(
                "Added to Queue/Download: %s",
                self._listener.name,
            )

            async with task_dict_lock:
                task_dict[self._listener.mid] = QueueStatus(
                    self._listener,
                    self._gid,
                    "dl",
                )

            await event.wait()

            if self._listener.is_cancelled:
                return

            LOGGER.info(
                "Start Queued Download from YT-DLP: %s",
                self._listener.name,
            )

            await self._on_download_start(True)

        if not add_to_queue:
            LOGGER.info(
                "Download with YT-DLP: %s",
                self._listener.name,
            )

        await sync_to_async(
            self._download,
            path,
        )

    async def cancel_task(self):
        self._listener.is_cancelled = True

        LOGGER.info(
            "Cancelling Download: %s",
            self._listener.name,
        )

        await self._listener.on_download_error(
            "Stopped by User!"
        )

    def _set_options(self, options):
        for key, value in options.items():

            if key == "postprocessors":
                if isinstance(value, list):
                    self.opts[key].extend(
                        tuple(value)
                    )

                elif isinstance(value, dict):
                    self.opts[key].append(value)

            elif key == "download_ranges":
                if isinstance(value, list):
                    self.opts[key] = (
                        lambda info, ytdl: value
                    )

            else:
                if (
                    key == "writethumbnail"
                    and value is True
                ):
                    self.keep_thumb = True

                self.opts[key] = value
