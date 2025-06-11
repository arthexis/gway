# tests/test_resource.py

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

    def test_text_mode_returns_string(self):
        path = gw.resource("textfile.txt", touch=True)
        path.write_text("some text")
        result = gw.resource("textfile.txt", text=True)
        self.assertEqual(result, "some text")

    def test_creates_intermediate_directories(self):
        path = gw.resource("a", "b", "c", "file.txt", touch=True)
        self.assertTrue(path.exists())
        self.assertTrue((self.base_path / "a" / "b" / "c").is_dir())

    def test_does_not_create_file_if_touch_false(self):
        path = gw.resource("nontouched.txt", touch=False)
        self.assertFalse(path.exists())

    def test_check_and_touch_together_creates_file(self):
        # Should NOT raise because touch=True allows creation
        path = gw.resource("create_and_check.txt", check=True, touch=True)
        self.assertTrue(path.exists())

    def test_text_mode_with_nonexistent_file_aborts(self):
        with self.assertRaises(SystemExit):  # Should fail reading
            gw.resource("no_such_file.txt", text=True)

    def test_returns_absolute_path_even_when_given_relative(self):
        result = gw.resource("relative.txt")
        self.assertTrue(result.is_absolute())
        self.assertTrue(str(result).startswith(str(self.base_path)))

    def test_read_text_works_with_unicode(self):
        path = gw.resource("unicode.txt", touch=True)
        content = "🎲🐍文字"
        path.write_text(content, encoding="utf-8")
        result = gw.resource("unicode.txt", text=True)
        self.assertEqual(result, content)

    def test_touch_then_text_returns_empty_string(self):
        # File exists but is empty
        path = gw.resource("empty.txt", touch=True)
        result = gw.resource("empty.txt", text=True)
        self.assertEqual(result, "")


if __name__ == "__main__":
    unittest.main()
