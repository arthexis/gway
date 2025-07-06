import unittest
import importlib.util
from pathlib import Path
from unittest.mock import patch

# Load the vbox module dynamically from projects directory
vbox_path = Path(__file__).resolve().parents[1] / "projects" / "vbox.py"
spec = importlib.util.spec_from_file_location("vbox", vbox_path)
vbox = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vbox)


class ViewDownloadsTests(unittest.TestCase):
    def setUp(self):
        # Patch render_error to capture calls
        self.render_patch = patch.object(
            vbox,
            "render_error",
            side_effect=lambda title, msg, **kw: {"title": title, "message": msg, "extra": kw},
        )
        self.mock_render = self.render_patch.start()

    def tearDown(self):
        self.render_patch.stop()

    def test_missing_vbid_returns_render_error(self):
        result = vbox.view_downloads(vbid=None)
        self.assertEqual(result["title"], "Missing vbid")
        self.assertIn("vbid", result["message"])


if __name__ == "__main__":
    unittest.main()
