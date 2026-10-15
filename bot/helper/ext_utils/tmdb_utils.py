import re
from asyncio import sleep
from difflib import SequenceMatcher
from os.path import splitext
from urllib.parse import unquote

from niquests import AsyncSession

from ... import LOGGER
from ...core.config_manager import Config

TMDB_SEARCH_URL = "https://api.themoviedb.org/3/search/multi"
TMDB_IMAGE_URL = "https://image.tmdb.org/t/p/original"

_QUALITY_TAGS = re.compile(
    r"\b(?:\d{3,4}p|4k|x26[45]|h\.?26[45]|hevc|avc|xvid|divx|aac\d?|ac3|eac3|ddp?\d(?:\.\d)?"
    r"|dts(?:-hd)?|truehd|atmos|hdr\d*|10bit|8bit|web-?dl|web-?rip|blu-?ray|bd-?rip"
    r"|br-?rip|hd-?rip|dvd-?rip|hdts|cam-?rip|hdtv|remux|repack|esubs?|msubs?|subbed"
    r"|dubbed|dsnp|amzn|hmax|hotstar|mkv|mp4|m4v|avi|webm|mpe?g|rar|zip|7z|part\d+)\b",
    re.IGNORECASE,
)
_SITE_PREFIX = re.compile(
    r"^\W*(?:www\.)?[\w-]+\.(?:com|net|org|xyz|me|in|to|co|cc|info|tv|link|app|online"
    r"|site|club|work|icu|top|vip|pro|party|fun|cam|lol|sbs|ws)"
    r"(?:\s*[-–—]+\s*|\s+)",
    re.IGNORECASE,
)

_poster_cache = {}
_imdb_image_cache = {}


def _tidy(title):
    title = re.sub(r"\s-+\s", " ", title)
    return re.sub(r"\s+", " ", title).strip(" -_.")


def _final_clean(title):
    base = re.sub(r"[\[\](){}]", " ", title)
    return _tidy(_QUALITY_TAGS.sub(" ", base)) or _tidy(base)


def clean_poster_title(raw_title):
    """Extract the actual movie/series name from a full path or release filename."""
    raw_title = unquote(str(raw_title or "")).replace("\\", "/")
    # The caller frequently passes an absolute file path, not just its filename.
    title = raw_title.rsplit("/", 1)[-1]
    stem, ext = splitext(title)
    if ext and len(ext) <= 9:
        title = stem

    title = re.sub(r"https?://\S+", " ", title)
    title = re.sub(r"\b(?:t|telegram)\.me/\S+", " ", title, flags=re.IGNORECASE)
    title = re.sub(r"\[[^\]]*\]", " ", title)
    title = re.sub(r"[\[\](){}]", " ", title)
    title = _SITE_PREFIX.sub("", title)
    title = re.sub(r"\bwww\S*", " ", title, flags=re.IGNORECASE)
    title = title.replace("_", " ")
    title = title.replace(".", " ")
    title = re.sub(r"\s+", " ", title).strip()

    # For episode releases, everything after SxxExxx is release noise. Keep
    # the show name only (e.g. My Hero Academia Vigilantes).
    for pattern in (
        r"(?<!\w)S0*\d{1,2}\s?E\d{1,3}(?!\w)",
        r"\bSeason\s+\d{1,2}\b",
        r"(?<!\w)S0*\d{1,2}(?!\w)",
        r"(?<!\w)(?:E|EP|EPISODE)\s?\d{1,4}(?!\w)",
    ):
        marker = re.search(pattern, title, re.IGNORECASE)
        if marker:
            head = title[: marker.start()].strip()
            tail = title[marker.end() :].strip()
            title = head if len(head) > 1 else tail
            return _final_clean(title), None

    years = list(re.finditer(r"\b(?:19|20)\d{2}\b", title))
    if years:
        last = years[-1]
        head = title[: last.start()].strip()
        tail = title[last.end() :].strip()
        return _final_clean(head if len(head) > 1 else tail), last.group(0)

    # If there is no year/episode marker, stop at the first technical release
    # token so encodes, languages, codecs, and uploader decorations are not
    # mistakenly sent to IMDb as part of the title.
    technical = re.search(
        r"\b(?:\d{3,4}p|4k|2160p|1080p|720p|480p|WEB[\s._-]*DL|WEB[\s._-]*RIP|"
        r"BLU[\s._-]*RAY|BD[\s._-]*RIP|BR[\s._-]*RIP|HDTV|HEVC|H[.]?26[45]|"
        r"X26[45]|XVID|DIVX|AAC(?:[\s._-]*\d(?:[.]\d)?)*|AC3|EAC3|DTS|TRUEHD|"
        r"ESUBS?|MSUBS?|SUBBED|DUBBED)\b",
        title,
        re.IGNORECASE,
    )
    if technical and technical.start() > 1:
        title = title[: technical.start()].strip()
    title = re.sub(r"[~|]+.*$", " ", title).strip()
    return _final_clean(title), None


def _pick_image(images, as_doc):
    backdrops = images.get("backdrops", [])
    posters = images.get("posters", [])
    en_backdrops = [i for i in backdrops if i.get("iso_639_1") == "en"]
    no_lang_backdrops = [i for i in backdrops if i.get("iso_639_1") is None]
    en_posters = [i for i in posters if i.get("iso_639_1") == "en"]
    no_lang_posters = [i for i in posters if i.get("iso_639_1") is None]

    if as_doc:
        order = [en_posters, no_lang_posters, posters, en_backdrops, no_lang_backdrops]
    else:
        order = [en_backdrops, no_lang_backdrops, backdrops, en_posters, posters]

    for group in order:
        if group:
            return group[0]["file_path"]
    return None


def _tmdb_token():
    return str(Config.TMDB_ACCESS_TOKEN or "").strip()


async def get_tmdb_poster_link(title, year=None, as_doc=False):
    token = _tmdb_token()
    if not token:
        return None

    headers = {"accept": "application/json"}
    params = {
        "query": title,
        "include_adult": "false",
        "language": "en-US",
        "page": "1",
    }
    if len(token) < 50:
        params["api_key"] = token
    else:
        headers["Authorization"] = f"Bearer {token}"

    for attempt in range(3):
        try:
            async with AsyncSession() as client:
                resp = await client.get(TMDB_SEARCH_URL, params=params, headers=headers, timeout=15)
                if resp.status_code == 401:
                    LOGGER.warning("TMDb authentication failed, check TMDB_ACCESS_TOKEN")
                    return None
                if resp.status_code >= 500:
                    await sleep(2)
                    continue
                if resp.status_code != 200:
                    LOGGER.warning(f"TMDb returned {resp.status_code} for '{title}'")
                    return None

                results = [
                    r
                    for r in resp.json().get("results", [])
                    if r.get("media_type") != "person"
                ]
                if not results:
                    LOGGER.info(f"No TMDb results for '{title}'")
                    return None

                first = results[0]
                if year:
                    for result in results:
                        date = (
                            result.get("release_date")
                            or result.get("first_air_date")
                            or ""
                        )
                        if date.startswith(year):
                            first = result
                            break
                media_type = first.get("media_type", "movie")

                img_params = {"include_image_language": "en,null"}
                if len(token) < 50:
                    img_params["api_key"] = token
                img_resp = await client.get(
                    f"https://api.themoviedb.org/3/{media_type}/{first['id']}/images",
                    params=img_params,
                    headers=headers,
                )
                if img_resp.status_code == 200:
                    path = _pick_image(img_resp.json(), as_doc)
                    if path:
                        return f"{TMDB_IMAGE_URL}{path}"

                backdrop = first.get("backdrop_path")
                poster = first.get("poster_path")
                fallback = (poster or backdrop) if as_doc else (backdrop or poster)
                if fallback:
                    return f"{TMDB_IMAGE_URL}{fallback}"
                return None
        except Exception as e:
            LOGGER.warning(f"TMDb request failed ({attempt + 1}/3): {e}")
            await sleep(1)
    return None


def _normalize_title(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


async def get_imdb_thumbnail_link(title, year=None, as_doc=False):
    """Find a title on IMDb and select a poster (documents) or a landscape still (video)."""
    from .bot_utils import sync_to_async

    cache_key = (title.casefold(), str(year or ""), bool(as_doc))
    if cache_key in _imdb_image_cache:
        return _imdb_image_cache[cache_key]

    try:
        from imdbio import get_media_gallery, get_movie, search_title

        search_year = int(year) if str(year or "").isdigit() else None
        search_result = await sync_to_async(
            search_title, title, year=search_year, locale="en"
        )
        candidates = list(getattr(search_result, "titles", None) or [])
        if not candidates:
            _imdb_image_cache[cache_key] = None
            return None

        target = _normalize_title(title)

        def candidate_score(candidate):
            candidate_title = getattr(candidate, "title", "")
            normalized = _normalize_title(candidate_title)
            similarity = SequenceMatcher(None, target, normalized).ratio()
            kind = str(getattr(candidate, "kind", "") or "").casefold()
            # A series release filename is cleaned to its show name, so prefer
            # the series title over a similarly named episode or movie.
            if "series" in kind or "miniseries" in kind:
                similarity += 0.08
            elif "episode" in kind:
                similarity -= 0.08
            if search_year and str(getattr(candidate, "year", "")) == str(search_year):
                similarity += 0.04
            return similarity

        candidates.sort(key=candidate_score, reverse=True)
        for candidate in candidates[:4]:
            imdb_id = (
                getattr(candidate, "imdbId", None)
                or getattr(candidate, "imdb_id", None)
                or getattr(candidate, "id", None)
            )
            if not imdb_id:
                continue

            cover_url = getattr(candidate, "cover_url", None)
            # IMDb's title cover is the portrait poster, ideal for document mode.
            if as_doc and cover_url:
                _imdb_image_cache[cache_key] = cover_url
                return cover_url

            gallery = await sync_to_async(get_media_gallery, str(imdb_id), locale="en")
            items = list(getattr(gallery, "items", None) or [])

            def image_shape(item):
                width = getattr(item, "width", None) or 0
                height = getattr(item, "height", None) or 0
                try:
                    width, height = int(width), int(height)
                except (TypeError, ValueError):
                    width, height = 0, 0
                image_type = str(getattr(item, "type", "") or "").casefold()
                return width, height, image_type

            if as_doc:
                # Prefer genuine portrait posters from the gallery.
                for item in items:
                    width, height, image_type = image_shape(item)
                    if getattr(item, "url", None) and (
                        (width > 0 and height > 0 and height > width)
                        or "poster" in image_type
                        or "portrait" in image_type
                    ):
                        _imdb_image_cache[cache_key] = item.url
                        return item.url
                if cover_url:
                    _imdb_image_cache[cache_key] = cover_url
                    return cover_url
            else:
                # Media output is video, so use the first landscape still/backdrop.
                for item in items:
                    width, height, image_type = image_shape(item)
                    is_landscape = width > height > 0
                    is_wide_type = any(
                        tag in image_type
                        for tag in ("backdrop", "landscape", "still", "frame")
                    )
                    if getattr(item, "url", None) and (is_landscape or is_wide_type):
                        _imdb_image_cache[cache_key] = item.url
                        return item.url

            # Try detail data only as a poster fallback; never substitute a
            # portrait as a video backdrop here.
            if as_doc:
                detail = await sync_to_async(get_movie, str(imdb_id), locale="en")
                detail_cover = getattr(detail, "cover_url", None) if detail else None
                if detail_cover:
                    _imdb_image_cache[cache_key] = detail_cover
                    return detail_cover

        _imdb_image_cache[cache_key] = None
        return None
    except Exception as exc:
        # IMDb can be temporarily rate-limited/WAF-blocked; TMDb or local-frame
        # fallback remains available, so thumbnail creation should never fail.
        LOGGER.debug("IMDb auto-thumbnail lookup failed for '%s': %s", title, exc)
        return None


async def get_auto_thumbnail(filename, as_doc=False):
    from .media_utils import download_image_thumb

    title, year = clean_poster_title(filename)
    if len(title) < 2:
        return None

    key = (title, year, bool(as_doc))
    poster_url = _poster_cache.get(key)
    if not poster_url:
        # IMDb is the primary no-token source. The full release filename is
        # cleaned above, e.g. "My Hero Academia Vigilantes S01E12 ..." becomes
        # only "My Hero Academia Vigilantes" before search.
        poster_url = await get_imdb_thumbnail_link(title, year, as_doc)
        if not poster_url:
            poster_url = await get_tmdb_poster_link(title, year, as_doc)
        if not poster_url:
            return None
        if len(_poster_cache) > 200:
            _poster_cache.clear()
        _poster_cache[key] = poster_url

    LOGGER.info("Auto thumbnail selected for '%s' (mode=%s)", title, "portrait" if as_doc else "landscape")
    return await download_image_thumb(poster_url) or None
