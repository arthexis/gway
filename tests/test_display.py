import unittest
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import datetime
from unittest.mock import patch
import os
from PIL import Image

class DisplayImageTests(unittest.TestCase):
    def _load_screen(self):
        spec = importlib.util.spec_from_file_location(
            "screen", Path(__file__).resolve().parents[1] / "projects" / "studio" / "screen.py"
        )
        screen = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(screen)
        return screen

    def _fake_resource_factory(self, tmpdir):
        def fake_resource(*parts, **kwargs):
            path = Path(tmpdir).joinpath(*parts)
            if kwargs.get("dir"):
                path.mkdir(parents=True, exist_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                if kwargs.get("touch") and not path.exists():
                    path.touch()
            return path
        return fake_resource

    def test_display_specific_path(self):
        screen = self._load_screen()
        with TemporaryDirectory() as tmp:
            screen.gw.resource = self._fake_resource_factory(tmp)
            img_path = screen.gw.resource("work", "img.png")
            Image.new("RGB", (10, 10), "red").save(img_path)
            with patch("PIL.Image.Image.show") as mock_show:
                result = screen.display("work/img.png")
            self.assertEqual(result, str(img_path))
            mock_show.assert_called_once()

    def test_display_latest_and_before(self):
        screen = self._load_screen()
        with TemporaryDirectory() as tmp:
            screen.gw.resource = self._fake_resource_factory(tmp)
            img_old = screen.gw.resource("work", "old.png")
            img_new = screen.gw.resource("work", "new.png")
            Image.new("RGB", (10, 10), "red").save(img_old)
            Image.new("RGB", (10, 10), "blue").save(img_new)
            t1 = datetime(2023, 1, 1, 12, 0).timestamp()
            t2 = datetime(2023, 1, 2, 12, 0).timestamp()
            os.utime(img_old, (t1, t1))
            os.utime(img_new, (t2, t2))
            with patch("PIL.Image.Image.show"):
                result = screen.display()
            self.assertEqual(result, str(img_new))
            before = datetime.fromtimestamp(t2 - 1).isoformat()
            with patch("PIL.Image.Image.show"):
                result_before = screen.display(before=before)
            self.assertEqual(result_before, str(img_old))

    def test_display_no_images_raises(self):
        screen = self._load_screen()
        with TemporaryDirectory() as tmp:
            screen.gw.resource = self._fake_resource_factory(tmp)
            with self.assertRaises(FileNotFoundError):
                screen.display()

    def test_display_missing_file_raises(self):
        screen = self._load_screen()
        with TemporaryDirectory() as tmp:
            screen.gw.resource = self._fake_resource_factory(tmp)
            with self.assertRaises(FileNotFoundError):
                screen.display("work/missing.png")

    def test_display_invalid_before_raises(self):
        screen = self._load_screen()
        with TemporaryDirectory() as tmp:
            screen.gw.resource = self._fake_resource_factory(tmp)
            with self.assertRaises(ValueError):
                screen.display(before="not-a-date")


if __name__ == "__main__":
    unittest.main()
