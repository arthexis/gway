import unittest
import tempfile
import os
import importlib.util
import types
import sys
from pathlib import Path

# Load site module for pseudo package structure
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
        html = release_mod.view_changelog()
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
        html = release_mod.view_changelog()
        self.assertIn("Unreleased", html)


if __name__ == "__main__":
    unittest.main()
