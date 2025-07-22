import unittest
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
import os


class OpenRemoteTests(unittest.TestCase):
    @staticmethod
    def _load_vbox():
        vbox_path = Path(__file__).resolve().parents[1] / "projects" / "vbox.py"
        spec = importlib.util.spec_from_file_location("vbox", vbox_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_open_remote_with_url_credentials(self):
        url = "https://example.com/vbox/uploads?vbid=test123"
        with TemporaryDirectory() as tmp:
            os.environ["GWAY_ROOT"] = tmp
            cdv_dir = Path(tmp) / "work" / "vbox"
            cdv_dir.mkdir(parents=True, exist_ok=True)
            (cdv_dir / "remotes.cdv").touch()
            cwd = os.getcwd()
            os.chdir(tmp)
            try:
                vbox = self._load_vbox()
                result = vbox.open_remote(url)
            finally:
                os.chdir(cwd)
                del os.environ["GWAY_ROOT"]
            self.assertIsNotNone(result)
            self.assertEqual(result.get("vbox"), "test123")
            self.assertEqual(result.get("url"), url)
            cdv_path = cdv_dir / "remotes.cdv"
            self.assertTrue(cdv_path.exists())
            content = cdv_path.read_text().strip()
            self.assertIn("test123", content)


if __name__ == "__main__":
    unittest.main()
