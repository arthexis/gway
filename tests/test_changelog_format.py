import unittest
import tempfile
import os
from pathlib import Path

# Load release module as in other tests
from gway import gw


class ChangelogUpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.old_cwd = Path.cwd()
        os.chdir(self.base)

    def tearDown(self):
        os.chdir(self.old_cwd)
        self.tmp.cleanup()

    def _write_changelog(self, text: str):
        Path("CHANGELOG.rst").write_text(text)

    def test_update_changelog_underline_matches_header(self):
        content = """Changelog
=========

Unreleased
----------
- first change
"""
        self._write_changelog(content)
        gw.release.update_changelog("1.2.3", "abcdef")
        text = Path("CHANGELOG.rst").read_text()
        lines = text.splitlines()
        header = "1.2.3 [build abcdef]"
        idx = lines.index(header)
        underline = lines[idx + 1]
        self.assertEqual(len(underline), len(header))

if __name__ == "__main__":
    unittest.main()
