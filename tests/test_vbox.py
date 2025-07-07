import unittest
import importlib.util
from pathlib import Path
from tempfile import NamedTemporaryFile
import os

# Dynamically load the vbox project module
vbox_path = Path(__file__).resolve().parents[1] / "projects" / "vbox.py"
spec = importlib.util.spec_from_file_location("vbox", vbox_path)
vbox = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vbox)


class StreamFileResponseTests(unittest.TestCase):
    def test_stream_file_response(self):
        content = b"Hello vbox"
        with NamedTemporaryFile(delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        try:
            resp = vbox.stream_file_response(tmp_path, "file.txt")
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
    def test_sanitize_filename(self):
        cases = {
            "foo/bar": "foobar",
            "../secret": "secret",
            "normal-name.txt": "normal-name.txt",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(vbox._sanitize_filename(raw), expected)


if __name__ == "__main__":
    unittest.main()
