import os
import unittest
import tempfile
from pathlib import Path
from gway import gw


class ResourceTests(unittest.TestCase):

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.tempdir.name)
        gw.base_path = self.base_path

    def tearDown(self):
        self.tempdir.cleanup()

    def test_relative_path_creation_with_touch(self):
        path = gw.resource("subdir", "file.txt", touch=True)
        self.assertTrue(path.exists())
        self.assertTrue(path.name == "file.txt")

    def test_absolute_path_skips_base_path(self):
        abs_path = self.base_path / "absolute.txt"
        result = gw.resource(str(abs_path), touch=True)
        self.assertEqual(result, abs_path)
        self.assertTrue(abs_path.exists())

    def test_check_missing_file_raises(self):
        missing = self.base_path / "missing.txt"
        with self.assertRaises(SystemExit):  # from gw.abort
            gw.resource(str(missing), check=True)

    def test_ext_inference_applied(self):
        path = gw.resource("file", ext=".txt", touch=True)
        self.assertTrue(str(path).endswith(".txt"))
        self.assertTrue(path.exists())

    def test_ext_inference_prioritizes_existing(self):
        raw = self.base_path / "existing"
        raw_txt = raw.with_suffix(".txt")
        raw_txt.write_text("hello")
        result = gw.resource("existing", ext=".txt")
        self.assertEqual(result.read_text(), "hello")

    def test_truncate_clears_file_contents(self):
        path = gw.resource("truncate.txt", touch=True)
        path.write_text("not empty")
        gw.resource("truncate.txt", truncate=True)
        self.assertEqual(path.read_text(), "")

    def test_text_mode_returns_string(self):
        path = gw.resource("textfile.txt", touch=True)
        path.write_text("some text")
        result = gw.resource("textfile.txt", text=True)
        self.assertEqual(result, "some text")

    def test_lines_mode_returns_list_of_lines(self):
        path = gw.resource("lines.txt", touch=True)
        path.write_text("a\nb\nc")
        result = gw.resource("lines.txt", lines=True)
        self.assertEqual(result, ["a", "b", "c"])

    def test_fallback_to_non_ext_if_exists(self):
        noext = self.base_path / "datafile"
        noext.write_text("raw")
        result = gw.resource("datafile", ext=".txt")
        self.assertEqual(result.read_text(), "raw")

    def test_read_failure_triggers_abort(self):
        path = gw.resource("unreadable.txt", touch=True)
        os.chmod(path, 0o000)  # revoke permissions
        try:
            with self.assertRaises(SystemExit):
                _ = gw.resource("unreadable.txt", text=True)
        finally:
            os.chmod(path, 0o644)  # restore to avoid cleanup issues


if __name__ == "__main__":
    unittest.main()
