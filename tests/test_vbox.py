import unittest
import importlib.util
from pathlib import Path
from tempfile import NamedTemporaryFile
import os


class StreamFileResponseTests(unittest.TestCase):
    @staticmethod
    def _load_vbox():
        vbox_path = Path(__file__).resolve().parents[1] / "projects" / "vbox.py"
        spec = importlib.util.spec_from_file_location("vbox", vbox_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    @classmethod
    def setUpClass(cls):
        cls.vbox = cls._load_vbox()

    def test_stream_file_response(self):
        content = b"Hello vbox"
        with NamedTemporaryFile(delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        try:
            resp = self.vbox.stream_file_response(tmp_path, "file.txt")
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.headers.get("Content-Type"), "application/octet-stream")
            self.assertEqual(
                resp.headers.get("Content-Disposition"),
                'attachment; filename="file.txt"'
            )
            self.assertEqual(resp.body, content)
        finally:
            os.remove(tmp_path)


class SanitizeFilenameTests(unittest.TestCase):
    @staticmethod
    def _load_vbox():
        vbox_path = Path(__file__).resolve().parents[1] / "projects" / "vbox.py"
        spec = importlib.util.spec_from_file_location("vbox", vbox_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    @classmethod
    def setUpClass(cls):
        cls.vbox = cls._load_vbox()

    def test_sanitize_filename(self):
        cases = {
            "foo/bar": "foobar",
            "../secret": "secret",
            "normal-name.txt": "normal-name.txt",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(self.vbox._sanitize_filename(raw), expected)


if __name__ == "__main__":
    unittest.main()
