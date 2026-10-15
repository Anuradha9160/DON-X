from os.path import basename, splitext
from re import compile as re_compile
from pycountry import languages
from ..ext_utils.media_utils import get_streams, normalize_language_tag


class MetadataProcessor:
    _year_pattern = re_compile(r"\b(19|20)\d{2}\b")
    _sanitize_pattern = re_compile(r'[<>:"/\\?*]')

    def __init__(self):
        self.vars = {}
        self.audio_streams = []
        self.subtitle_streams = []

    @staticmethod
    def convert_lang_code(lang_code):
        if not lang_code:
            return lang_code
        clean = normalize_language_tag(lang_code)
        if not clean:
            return "unknown"
        try:
            if len(clean) == 2:
                lang = languages.get(alpha_2=clean.lower())
            elif len(clean) == 3:
                lang = languages.get(alpha_3=clean.lower())
            else:
                lang = languages.get(name=clean.title())
            return lang.name if lang else clean
        except Exception:
            return clean


    async def extract_file_vars(self, file_path):
        fname = basename(file_path)
        bname, ext = splitext(fname)
        self.vars = {
            "filename": fname,
            "basename": bname,
            "extension": ext.lstrip("."),
            "audiolang": "unknown",
            "sublang": "none",
        }
        self.audio_streams, self.subtitle_streams = [], []
        try:
            for s in await get_streams(file_path) or []:
                ctype = s.get("codec_type", "").lower()
                slang = s.get("tags", {}).get("language", "unknown")
                full_lang = self.convert_lang_code(slang)
                entry = {
                    "index": s.get("index", 0),
                    "language": slang,
                    "full_language": full_lang,
                }
                if ctype == "audio":
                    self.audio_streams.append(entry)
                    if self.vars["audiolang"] == "unknown" and slang != "und":
                        self.vars["audiolang"] = full_lang
                elif ctype == "subtitle":
                    self.subtitle_streams.append(entry)
                    if self.vars["sublang"] == "none" and slang != "und":
                        self.vars["sublang"] = full_lang
        except Exception:
            pass
        m = self._year_pattern.findall(bname)
        if m:
            self.vars["year"] = m[-1]

    @staticmethod
    def parse_string(metadata_str):
        if not metadata_str or not isinstance(metadata_str, str):
            return {}
        parts, current, i = [], "", 0
        while i < len(metadata_str):
            if (
                metadata_str[i] == "\\"
                and i + 1 < len(metadata_str)
                and metadata_str[i + 1] == "|"
            ):
                current += "|"
                i += 2
            elif metadata_str[i] == "|":
                parts.append(current)
                current = ""
                i += 1
            else:
                current += metadata_str[i]
                i += 1
        if current:
            parts.append(current)
        return dict(p.split("=", 1) if "=" in p else (p, "") for p in parts)

    @staticmethod
    def merge_dicts(default_dict, cmd_dict):
        return {**(default_dict or {}), **(cmd_dict or {})}

    def apply_vars_to_stream(
        self, metadata_dict, stream_lang=None, full_lang=None, stream_type="audio"
    ):
        if not isinstance(metadata_dict, dict):
            return {}
        vars_with_stream = self.vars.copy()
        if stream_lang and stream_lang != "unknown":
            key = "audiolang" if stream_type == "audio" else "sublang"
            vars_with_stream[key] = full_lang or self.convert_lang_code(stream_lang)
        return {
            self.sanitize(k): (
                str(v).format(**vars_with_stream) if isinstance(v, str) else str(v)
            )
            for k, v in metadata_dict.items()
        }

    def apply_vars(self, metadata_dict):
        return self.apply_vars_to_stream(metadata_dict)

    def get_audio_metadata(self, audio_metadata_dict):
        return [
            {
                "index": s["index"],
                "metadata": self.apply_vars_to_stream(
                    audio_metadata_dict, s["language"], s["full_language"], "audio"
                ),
            }
            for s in self.audio_streams
        ]

    def get_subtitle_metadata(self, subtitle_metadata_dict):
        return [
            {
                "index": s["index"],
                "metadata": self.apply_vars_to_stream(
                    subtitle_metadata_dict,
                    s["language"],
                    s["full_language"],
                    "subtitle",
                ),
            }
            for s in self.subtitle_streams
        ]

    def sanitize(self, value):
        return self._sanitize_pattern.sub("_", str(value))[:100]

    @staticmethod
    def route_global_title_to_video(global_metadata, video_metadata, streams):
        """Route generic title metadata to a real video stream, never audio/subtitles.

        The generic metadata title is removed from container-level metadata. If a
        real video stream exists, it becomes its stream title. Attached cover-art
        streams do not count as videos.
        """
        if not isinstance(global_metadata, dict):
            return
        title_items = [(key, value) for key, value in global_metadata.items()
                       if str(key).strip().lower() == "title"]
        if not title_items:
            return
        # Last configured title wins, then remove every spelling/case variant.
        title_value = title_items[-1][1]
        for key, _ in title_items:
            global_metadata.pop(key, None)
        if title_value is None or not str(title_value).strip():
            return
        has_video = any(
            str(stream.get("codec_type", "")).lower() == "video"
            and not bool((stream.get("disposition") or {}).get("attached_pic", 0))
            for stream in (streams or [])
        )
        if not has_video or not isinstance(video_metadata, dict):
            return
        # The generic title is the configured title value (not a note to
        # append); collapse case variants to one canonical video-stream tag.
        for key in list(video_metadata):
            if str(key).strip().lower() == "title":
                video_metadata.pop(key, None)
        video_metadata["title"] = str(title_value)

    async def process_all(
        self,
        video_metadata_dict,
        audio_metadata_dict,
        subtitle_metadata_dict,
        file_path,
    ):
        await self.extract_file_vars(file_path)
        return {
            "video": (
                self.apply_vars(video_metadata_dict) if video_metadata_dict else {}
            ),
            "audio_streams": (
                self.get_audio_metadata(audio_metadata_dict)
                if audio_metadata_dict
                else []
            ),
            "subtitle_streams": (
                self.get_subtitle_metadata(subtitle_metadata_dict)
                if subtitle_metadata_dict
                else []
            ),
            "global": {},
        }

    async def process(self, metadata_dict, file_path):
        await self.extract_file_vars(file_path)
        return self.apply_vars(metadata_dict)
