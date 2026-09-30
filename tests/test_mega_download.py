import unittest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch

from mega.errors import RequestError

from bot.helper.ext_utils.links_utils import (
    is_mega_link,
    is_mega_folder_link,
    get_mega_subfolder_handle,
)
from bot.helper.listeners.mega_listener import (
    _call_attr,
    _mega_error_format,
    _get_node_name,
    _get_node_handle,
    _get_node_size,
    _is_node_folder,
)
from bot.helper.mirror_leech_utils.download_utils.mega_download import (
    MegaPyStatusHelper,
    _reserve_link,
    _release_link,
    _mega_py_get_instance,
    _mega_py_fetch_info,
)
from bot.helper.mirror_leech_utils.status_utils.mega_status import MegaDownloadStatus


class TestMegaDownload(unittest.IsolatedAsyncioTestCase):

    def test_mega_link_utils(self):
        # File links
        file_url1 = "https://mega.nz/file/abc12345#xyz98765"
        file_url2 = "https://mega.nz/#!abc12345!xyz98765"
        self.assertTrue(is_mega_link(file_url1))
        self.assertTrue(is_mega_link(file_url2))
        self.assertFalse(is_mega_folder_link(file_url1))
        self.assertFalse(is_mega_folder_link(file_url2))

        # Folder links
        folder_url1 = "https://mega.nz/folder/folder123#key456"
        folder_url2 = "https://mega.nz/#F!folder123!key456"
        subfolder_url = "https://mega.nz/folder/folder123#key456/folder/sub789"

        self.assertTrue(is_mega_link(folder_url1))
        self.assertTrue(is_mega_folder_link(folder_url1))
        self.assertTrue(is_mega_folder_link(folder_url2))
        self.assertTrue(is_mega_folder_link(subfolder_url))

        # Subfolder handle extraction
        self.assertEqual(get_mega_subfolder_handle(subfolder_url), "sub789")
        self.assertIsNone(get_mega_subfolder_handle(folder_url1))

    def test_call_attr_swig_safety(self):
        class MockSwigObject:
            def __init__(self):
                self.int_val = -13
                self.str_val = "hello"

            def method_val(self):
                return 42

        obj = MockSwigObject()

        # Callable method
        self.assertEqual(_call_attr(obj, "method_val", 0), 42)
        # Integer attribute (non-callable)
        self.assertEqual(_call_attr(obj, "int_val", 0), -13)
        # String attribute
        self.assertEqual(_call_attr(obj, "str_val", ""), "hello")
        # Missing attribute
        self.assertEqual(_call_attr(obj, "non_existent", -1), -1)
        # None object
        self.assertIsNone(_call_attr(None, "anything", None))

    def test_mega_error_format(self):
        self.assertEqual(_mega_error_format("-13"), "Incomplete transfer")
        self.assertEqual(_mega_error_format("-9"), "File(s) not found or deleted")
        self.assertEqual(_mega_error_format("Unknown error string"), "Unknown error string")

    def test_node_helper_functions(self):
        class MockNode:
            def getName(self):
                return "test_file.mkv"

            def getHandle(self):
                return "node_handle_123"

            def getSize(self):
                return 1048576

            def isFolder(self):
                return False

        node = MockNode()
        self.assertEqual(_get_node_name(node), "test_file.mkv")
        self.assertEqual(_get_node_handle(node), "node_handle_123")
        self.assertEqual(_get_node_size(node), 1048576)
        self.assertFalse(_is_node_folder(node))

    def test_megapy_status_helper(self):
        class DummyListener:
            def __init__(self):
                self.name = "Test_Video.mp4"
                self.size = 100000000
                self.is_cancelled = False

            async def on_download_error(self, msg, is_limit=False):
                pass

        listener = DummyListener()
        status_helper = MegaPyStatusHelper(listener, "gid12345")

        status_helper.downloaded_bytes = 50000000
        status_helper.speed_val = 5000000

        self.assertEqual(status_helper.name(), "Test_Video.mp4")
        self.assertEqual(status_helper.progress_raw(), 50.0)
        self.assertEqual(status_helper.progress(), "50.0%")
        self.assertEqual(status_helper.processed_bytes(), "47.68MB")
        self.assertEqual(status_helper.speed(), "4.77MB/s")
        self.assertEqual(status_helper.gid(), "gid12345")

    def test_mega_download_status(self):
        class DummyListener:
            def __init__(self):
                self.name = "Folder_Archive"
                self.size = 200000000
                self.is_cancelled = False

        class DummyListenerObj:
            def __init__(self):
                self.downloaded_bytes = 100000000
                self.speed = 10000000

            async def cancel_task(self):
                pass

        listener = DummyListener()
        obj = DummyListenerObj()
        status = MegaDownloadStatus(listener, obj, "gid67890", "dl")

        self.assertEqual(status.name(), "Folder_Archive")
        self.assertEqual(status.progress_raw(), 50.0)
        self.assertEqual(status.progress(), "50.0%")
        self.assertEqual(status.speed(), "9.54MB/s")
        self.assertEqual(status.gid(), "gid67890")

    async def test_reserve_release_link(self):
        test_link = "https://mega.nz/file/testlink123#testkey"

        res1 = await _reserve_link(test_link)
        self.assertTrue(res1)

        # Reserving same link again should return False
        res2 = await _reserve_link(test_link)
        self.assertFalse(res2)

        await _release_link(test_link)

        # Reserving again after release should return True
        res3 = await _reserve_link(test_link)
        self.assertTrue(res3)
        await _release_link(test_link)

    @patch("mega.Mega.login")
    def test_mega_py_get_instance_eaccess_fallback(self, mock_login):
        mock_login.side_effect = RequestError(-11)
        instance = _mega_py_get_instance()
        self.assertIsNotNone(instance)
        self.assertIsNone(instance.sid)

    @patch("bot.helper.mirror_leech_utils.download_utils.mega_download._mega_py_get_instance")
    def test_mega_py_fetch_info_eaccess_retry(self, mock_get_instance):
        class DummyListener:
            def __init__(self):
                self.link = "https://mega.nz/file/abc12345#xyz98765432101234567890"
                self.name = ""
                self.size = 0

        listener = DummyListener()
        mock_m1 = MagicMock()
        mock_m1._parse_url.return_value = "abc12345!key"
        mock_m1._api_request.side_effect = RequestError(-11)
        mock_get_instance.return_value = mock_m1

        with patch("mega.Mega._api_request") as mock_unauth_api_req, \
             patch("mega.crypto.base64_to_a32", return_value=(1, 2, 3, 4, 5, 6, 7, 8)):
            import mega.crypto as c
            # Valid encrypted attributes for "test_file.txt"
            k = (1 ^ 5, 2 ^ 6, 3 ^ 7, 4 ^ 8)
            at_enc = c.base64_url_encode(c.encrypt_attr({"n": "test_file.txt"}, k))
            mock_unauth_api_req.return_value = {
                "g": "https://g.api.mega.co.nz/test",
                "s": 2048,
                "at": at_enc,
            }

            info = _mega_py_fetch_info(listener, None, None)
            self.assertFalse(info["is_folder"])
            self.assertEqual(info["file_name"], "test_file.txt")
            self.assertEqual(info["file_size"], 2048)


if __name__ == "__main__":
    unittest.main()
