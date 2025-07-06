import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from gway import gw

# Load nav module dynamically
import importlib.util
nav_path = Path(__file__).resolve().parents[1] / "projects" / "web" / "nav.py"
spec = importlib.util.spec_from_file_location("webnav", nav_path)
webnav = importlib.util.module_from_spec(spec)
spec.loader.exec_module(webnav)


class ListStylesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.global_dir = base / "data" / "static" / "styles"
        self.proj_dir = base / "data" / "static" / "myproj" / "styles"
        self.global_dir.mkdir(parents=True)
        self.proj_dir.mkdir(parents=True)
        # Global css files
        (self.global_dir / "base.css").write_text("base")
        (self.global_dir / "extra.css").write_text("extra")
        (self.global_dir / "shared.css").write_text("shared")
        # Non-css file should be ignored
        (self.global_dir / "README.txt").write_text("ignore")
        # Project css files
        (self.proj_dir / "proj.css").write_text("proj")
        (self.proj_dir / "shared.css").write_text("duplicate")

    def tearDown(self):
        self.tmp.cleanup()

    def _fake_resource(self, *parts, **kwargs):
        return Path(self.tmp.name).joinpath(*parts)

    def test_lists_global_styles_only(self):
        with patch.object(gw, "resource", side_effect=self._fake_resource):
            styles = webnav.list_styles()
            names = [f for _, f in styles]
            self.assertEqual(names, ["base.css", "extra.css", "shared.css"])

    def test_lists_project_styles_without_duplicates(self):
        with patch.object(gw, "resource", side_effect=self._fake_resource):
            styles = webnav.list_styles("myproj")
            self.assertEqual(styles, [
                ("global", "base.css"),
                ("global", "extra.css"),
                ("global", "shared.css"),
                ("myproj", "proj.css"),
            ])


if __name__ == "__main__":
    unittest.main()
