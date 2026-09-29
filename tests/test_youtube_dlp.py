import pytest
import shutil
from bot.helper.ext_utils.links_utils import is_youtube_link
from bot.modules.ytdlp import find_node_executable, extract_info


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
