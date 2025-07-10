import os
import unittest
import tempfile
from pathlib import Path
from gway import gw

SUITE = "resource"

class ResourceTests(unittest.TestCase):

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.tempdir.name)
        self._old_cwd = Path.cwd()
        os.chdir(self.base_path)

    def tearDown(self):
        os.chdir(self._old_cwd)
        self.tempdir.cleanup()

    def test_relative_path_creation_with_touch(self):
        path = gw.resource("work", "test", SUITE, "test_relative_path_creation_with_touch", "subdir", "file.txt", touch=True)
        self.assertTrue(path.exists())
        self.assertTrue(path.name == "file.txt")

    def test_absolute_path_skips_base_path(self):
        abs_path = self.base_path / "work" / "test" / SUITE / "test_absolute_path_skips_base_path" / "absolute.txt"
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        result = gw.resource(str(abs_path), touch=True)
        self.assertEqual(result, abs_path)
        self.assertTrue(abs_path.exists())

    def test_check_missing_file_raises(self):
        missing = self.base_path / "work" / "test" / SUITE / "test_check_missing_file_raises" / "missing.txt"
        with self.assertRaises(SystemExit):  # from gw.abort
            gw.resource(str(missing), check=True)

    def test_text_mode_returns_string(self):
        testdir = "test_text_mode_returns_string"
        path = gw.resource("work", "test", SUITE, testdir, "textfile.txt", touch=True)
        path.write_text("some text")
        result = gw.resource("work", "test", SUITE, testdir, "textfile.txt", text=True)
        self.assertEqual(result, "some text")

    def test_creates_intermediate_directories(self):
        testdir = "test_creates_intermediate_directories"
        dir_path = gw.resource("work", "test", SUITE, testdir, "a", "b", "c", dir=True)
        self.assertTrue(dir_path.is_dir())
        self.assertTrue((self.base_path / "work" / "test" / SUITE / testdir / "a" / "b" / "c").is_dir())

    def test_does_not_create_file_if_touch_false(self):
        testdir = "test_does_not_create_file_if_touch_false"
        path = gw.resource("work", "test", SUITE, testdir, "nontouched.txt", touch=False)
        self.assertFalse(path.exists())

    def test_check_and_touch_together_creates_file(self):
        testdir = "test_check_and_touch_together_creates_file"
        path = gw.resource("work", "test", SUITE, testdir, "create_and_check.txt", check=True, touch=True)
        self.assertTrue(path.exists())

    def test_text_mode_with_nonexistent_file_aborts(self):
        testdir = "test_text_mode_with_nonexistent_file_aborts"
        with self.assertRaises(SystemExit):
            gw.resource("work", "test", SUITE, testdir, "no_such_file.txt", text=True)

    def test_returns_absolute_path_even_when_given_relative(self):
        testdir = "test_returns_absolute_path_even_when_given_relative"
        result = gw.resource("work", "test", SUITE, testdir, "relative.txt", touch=True)
        self.assertTrue(result.is_absolute())
        self.assertTrue(str(result).startswith(str(self.base_path)))

    def test_read_text_works_with_unicode(self):
        testdir = "test_read_text_works_with_unicode"
        path = gw.resource("work", "test", SUITE, testdir, "unicode.txt", touch=True)
        content = "🎲🐍文字"
        path.write_text(content, encoding="utf-8")
        result = gw.resource("work", "test", SUITE, testdir, "unicode.txt", text=True)
        self.assertEqual(result, content)

    def test_touch_then_text_returns_empty_string(self):
        testdir = "test_touch_then_text_returns_empty_string"
        path = gw.resource("work", "test", SUITE, testdir, "empty.txt", touch=True)
        result = gw.resource("work", "test", SUITE, testdir, "empty.txt", text=True)
        self.assertEqual(result, "")

    def test_parents_false_does_not_create_directories(self):
        testdir = "test_parents_false_does_not_create_directories"
        path = gw.resource("work", "test", SUITE, testdir, "file.txt", parents=False)
        self.assertFalse(path.parent.exists())

if __name__ == "__main__":
    unittest.main()
