import unittest
import tempfile
import os
from pathlib import Path

# Load release module as in other tests
import importlib.util
import types
import sys

# Setup pseudo package structure
site_spec = importlib.util.spec_from_file_location(
    "projects.web.site",
    Path(__file__).resolve().parents[1] / "projects" / "web" / "site.py",
)
site_mod = importlib.util.module_from_spec(site_spec)
site_spec.loader.exec_module(site_mod)

projects_mod = types.ModuleType("projects")
web_mod = types.ModuleType("projects.web")
web_mod.site = site_mod
projects_mod.web = web_mod
sys.modules.setdefault("projects", projects_mod)
sys.modules.setdefault("projects.web", web_mod)
sys.modules.setdefault("projects.web.site", site_mod)

# Load release module
release_spec = importlib.util.spec_from_file_location(
    "projects.release",
    Path(__file__).resolve().parents[1] / "projects" / "release.py",
)
release_mod = importlib.util.module_from_spec(release_spec)
release_spec.loader.exec_module(release_mod)

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
        release_mod.update_changelog("1.2.3", "abcdef")
        text = Path("CHANGELOG.rst").read_text()
        lines = text.splitlines()
        header = "1.2.3 [build abcdef]"
        idx = lines.index(header)
        underline = lines[idx + 1]
        self.assertEqual(len(underline), len(header))

if __name__ == "__main__":
    unittest.main()
