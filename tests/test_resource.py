import os
import unittest
import tempfile
from pathlib import Path
from gway import gw

# TODO: Clean the files used for testing beforehand

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

if __name__ == "__main__":
    unittest.main()
