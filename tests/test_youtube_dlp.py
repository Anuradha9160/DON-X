import pytest
import shutil
from unittest.mock import MagicMock
from bot.helper.ext_utils.links_utils import is_youtube_link
from bot.modules.ytdlp import find_node_executable, extract_info, YtSelection


def test_is_youtube_link():
    valid_urls = [
        "https://www.youtube.com/watch?v=g53iFgFNVJI",
        "https://youtu.be/g53iFgFNVJI",
        "https://www.youtube.com/shorts/g53iFgFNVJI",
        "https://www.youtube.com/playlist?list=PL123456789",
        "https://music.youtube.com/watch?v=g53iFgFNVJI",
        "https://m.youtube.com/watch?v=g53iFgFNVJI",
        "https://www.youtube.com/live/g53iFgFNVJI",
        "https://www.youtube.com/embed/g53iFgFNVJI",
        "https://www.youtube.com/@ChannelName",
    ]
    for url in valid_urls:
        assert is_youtube_link(url) is True, f"Failed for {url}"

    invalid_urls = [
        "https://example.com/video.mp4",
        "https://drive.google.com/file/d/123",
        "https://t.me/channel/123",
        "",
        None,
    ]
    for url in invalid_urls:
        assert is_youtube_link(url) is False, f"Failed for {url}"


def test_find_node_executable():
    node_path = find_node_executable()
    assert node_path is not None
    assert "node" in node_path.lower()


def test_youtube_extract_info_real_video():
    url = "https://www.youtube.com/watch?v=g53iFgFNVJI"
    info = extract_info(url, {"usenetrc": True})
    assert info is not None
    assert "id" in info
    assert info["id"] == "g53iFgFNVJI"
    assert "title" in info


@pytest.mark.asyncio
async def test_yt_selection_formats_dynamic():
    mock_listener = MagicMock()
    mock_listener.user_id = 12345
    mock_listener.message = MagicMock()

    selection = YtSelection(mock_listener)

    # Mock video info without 1080p (only 360p and 720p available)
    mock_result = {
        "formats": [
            {
                "format_id": "audio1",
                "ext": "m4a",
                "vcodec": "none",
                "acodec": "mp4a.40.2",
                "abr": 128,
                "filesize": 1000000,
            },
            {
                "format_id": "v360",
                "ext": "mp4",
                "height": 360,
                "vcodec": "avc1.4d401e",
                "acodec": "none",
                "tbr": 500,
                "filesize": 5000000,
            },
            {
                "format_id": "v720",
                "ext": "mp4",
                "height": 720,
                "vcodec": "avc1.4d401f",
                "acodec": "none",
                "tbr": 1500,
                "filesize": 15000000,
            },
        ]
    }

    # Intercept send_message to avoid network/TG calls
    from bot.modules import ytdlp
    original_send_message = ytdlp.send_message
    ytdlp.send_message = AsyncMockReturn(MagicMock())
    ytdlp.delete_message = AsyncMockReturn(True)

    try:
        selection.event.set()  # set event immediately so get_quality returns without waiting
        await selection.get_quality(mock_result)

        # Check stored formats
        format_names = [v["name"] for v in selection.formats.values() if isinstance(v, dict)]

        # Ensure 360p and 720p are present
        assert any("360p" in name for name in format_names)
        assert any("720p" in name for name in format_names)

        # Ensure unavailable resolutions like 1080p, 1440p, 2160p are NOT present
        assert not any("1080p" in name for name in format_names)
        assert not any("1440p" in name for name in format_names)

        # Ensure actual format IDs are used (e.g., v360+bestaudio/best)
        all_vformats = []
        for fmt in selection.formats.values():
            if isinstance(fmt, dict) and "items" in fmt:
                for item in fmt["items"].values():
                    all_vformats.append(item[1])

        assert "v360+bestaudio/best" in all_vformats
        assert "v720+bestaudio/best" in all_vformats
        assert "audio1" in all_vformats
    finally:
        ytdlp.send_message = original_send_message


class AsyncMockReturn:
    def __init__(self, return_value):
        self.return_value = return_value

    async def __call__(self, *args, **kwargs):
        return self.return_value
