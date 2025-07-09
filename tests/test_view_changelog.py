import unittest
import tempfile
import os
from pathlib import Path
from gway import gw

class ViewChangelogTests(unittest.TestCase):
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

    def test_header_hidden_when_empty(self):
        content = """Changelog
=========

Unreleased
----------

0.1.0 [build 123]
-----------------

- first change
"""
        self._write_changelog(content)
        html = gw.release.view_changelog()
        self.assertNotIn("Unreleased", html)

    def test_header_shown_when_has_entries(self):
        content = """Changelog
=========

Unreleased
----------
- new feature

0.1.0 [build 123]
-----------------

- first change
"""
        self._write_changelog(content)
        html = gw.release.view_changelog()
        self.assertIn("Unreleased", html)


if __name__ == "__main__":
    unittest.main()
