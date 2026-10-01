import unittest
import asyncio
from unittest.mock import MagicMock, AsyncMock

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

    def test_mega_py_fetch_info_credentials_and_fallback(self):
        from unittest.mock import patch
        from mega import Mega
        from bot.helper.mirror_leech_utils.download_utils.mega_download import _mega_py_fetch_info

        class DummyListener:
            def __init__(self):
                self.link = "https://mega.nz/file/zHgE1DwB#WBLS_qbRZ2qRZDhgK-r36J09Kd1lsV_eHG3jKbiUE04"
                self.name = ""
                self.size = 0

        listener = DummyListener()

        m_dummy = Mega()
        m_dummy._api_request = MagicMock(return_value={"g": "http://gfs.mega.co.nz/dl/test", "s": 12345, "at": "eA=="})

        with patch.object(Mega, "login", return_value=m_dummy) as mock_login, \
             patch("mega.crypto.decrypt_attr", return_value={"n": "test_file.mp4"}):

            # Test 1: With credentials -> mega.login(email, password) called
            _mega_py_fetch_info(listener, "test@example.com", "password123")
            mock_login.assert_called_with("test@example.com", "password123")

            # Reset mocks
            mock_login.reset_mock()

            # Test 2: Without credentials -> mega.login is NEVER called without args
            _mega_py_fetch_info(listener, None, None)
            mock_login.assert_not_called()

    def test_mega_py_api_request_patch_folder(self):
        from unittest.mock import patch
        from mega import Mega
        from bot.helper.mirror_leech_utils.download_utils.mega_download import _patch_mega_py

        _patch_mega_py()
        m = Mega()

        with patch("requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.text = '[{"f": []}]'
            mock_post.return_value = mock_resp

            # Call patched _api_request with folder data containing 'n'
            res = m._api_request({"a": "f", "c": 1, "r": 1, "ca": 1, "n": "folder_123"})

            # Verify 'n' was moved to params and removed from payload
            self.assertEqual(res, {"f": []})
            mock_post.assert_called_once()
            _, kwargs = mock_post.call_args
            self.assertIn("params", kwargs)
            self.assertEqual(kwargs["params"].get("n"), "folder_123")
            self.assertIn("data", kwargs)
            self.assertNotIn("folder_123", kwargs["data"])

    def test_mega_py_api_request_folder_id(self):
        from unittest.mock import patch
        from mega import Mega
        from bot.helper.mirror_leech_utils.download_utils.mega_download import _patch_mega_py

        _patch_mega_py()
        m = Mega()

        with patch("requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.text = '[{"g": "http://gfs.mega.co.nz/dl/test"}]'
            mock_post.return_value = mock_resp

            # Call patched _api_request with file data containing 'folder_id'
            res = m._api_request({"a": "g", "g": 1, "n": "node_123", "folder_id": "folder_456"})

            # Verify 'folder_id' was moved to params 'n'
            self.assertEqual(res, {"g": "http://gfs.mega.co.nz/dl/test"})
            mock_post.assert_called_once()
            _, kwargs = mock_post.call_args
            self.assertIn("params", kwargs)
            self.assertEqual(kwargs["params"].get("n"), "folder_456")
            self.assertIn("data", kwargs)
            self.assertNotIn("folder_456", kwargs["data"])

    def test_execute_mega_py_request_session_expired_recovery(self):
        from unittest.mock import patch
        from mega import Mega
        from bot.helper.mirror_leech_utils.download_utils.mega_download import _execute_mega_py_request

        m_expired = Mega()
        m_expired._api_request = MagicMock(side_effect=RuntimeError("ESID, Invalid or expired user session, please re-login"))

        m_new = Mega()
        m_new._api_request = MagicMock(return_value={"g": "http://gfs.mega.co.nz/dl/recovered", "s": 100})

        with patch.object(Mega, "login", return_value=m_new) as mock_login:
            res, m_returned = _execute_mega_py_request(
                m_expired, {"a": "g", "g": 1, "p": "test_pid"}, "user@test.com", "pass123"
            )
            mock_login.assert_called_once_with("user@test.com", "pass123")
            self.assertEqual(res, {"g": "http://gfs.mega.co.nz/dl/recovered", "s": 100})
            self.assertEqual(m_returned, m_new)

    def test_download_file_chunks_with_url_refresh_and_base_downloaded(self):
        from unittest.mock import patch
        import tempfile
        import os
        from bot.helper.mirror_leech_utils.download_utils.mega_download import _download_file_chunks

        status_helper = MagicMock()
        status_helper.downloaded_bytes = 100

        with tempfile.TemporaryDirectory() as tmpdir:
            dest_path = os.path.join(tmpdir, "test.bin")
            k_str = b"\x00" * 16
            iv = (0, 0)
            meta_mac = (0, 0)

            # Mock requests.get first to fail once, then succeed with refreshed url
            refresh_called = False
            def get_url_cb():
                nonlocal refresh_called
                refresh_called = True
                return "http://mega.nz/dl/refreshed"

            mock_res_fail = MagicMock()
            mock_res_fail.raise_for_status.side_effect = Exception("HTTP 403 Forbidden")

            mock_res_ok = MagicMock()
            mock_res_ok.raise_for_status.return_value = None
            mock_res_ok.iter_content.return_value = [b"\x00" * 16]

            with patch("requests.get", side_effect=[mock_res_fail, mock_res_ok]):
                res = _download_file_chunks(
                    "http://mega.nz/dl/initial",
                    16,
                    dest_path,
                    k_str,
                    iv,
                    meta_mac,
                    status_helper=status_helper,
                    get_url_cb=get_url_cb,
                    base_downloaded=100,
                )
                self.assertTrue(res)
                self.assertTrue(refresh_called)
                self.assertEqual(status_helper.downloaded_bytes, 116)

    def test_mega_py_fetch_info_nested_folder_decryption(self):
        from unittest.mock import patch
        from mega import Mega
        from bot.helper.mirror_leech_utils.download_utils.mega_download import _mega_py_fetch_info

        class DummyListener:
            def __init__(self):
                self.link = "https://mega.nz/folder/q3wC2aLY#u_BQd1aVz_JS-CDC11ZY2g"
                self.name = ""
                self.size = 0

        listener = DummyListener()

        # Mock nodes response containing multi-pair k values
        mock_nodes = {
            "f": [
                {
                    "h": "73xnAaJS",
                    "p": "root",
                    "t": 1,
                    "a": "Kfnxaxv-2V2ijv7-p2wbnmphnkvTIIPZPxljt4FSXI8",
                    "k": "73xnAaJS:0fOYSWm8l0KSvKLUrTbScA",
                },
                {
                    "h": "Xj5EGShB",
                    "p": "73xnAaJS",
                    "t": 1,
                    "a": "SeIwkt_6Qc-qHYej1OZtQlkis1VgzsZCSLgL6qpbq8c",
                    "k": "Xj5EGShB:KpShdj1lFnHu0vko39WPVg/73xnAaJS:OvuW4wIr4srxEnkZCzUv4w",
                },
            ]
        }

        m_dummy = Mega()
        m_dummy._api_request = MagicMock(return_value=mock_nodes)

        with patch("bot.helper.mirror_leech_utils.download_utils.mega_download._get_mega_session", return_value=m_dummy):
            info = _mega_py_fetch_info(listener, None, None)
            self.assertTrue(info["is_folder"])
            self.assertEqual(info["folder_id"], "q3wC2aLY")
            self.assertIn("root_name", info)


if __name__ == "__main__":
    unittest.main()
