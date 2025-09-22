import unittest
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
from PIL import Image
from unittest.mock import patch

class AnimateGifTests(unittest.TestCase):
    def test_animate_gif_produces_multiple_frames(self):
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            img1 = Image.new("RGB", (50, 50), "red")
            img2 = Image.new("RGB", (50, 50), "blue")
            img1.save(tmp_path / "frame-1.png")
            img2.save(tmp_path / "frame-2.png")

            spec = importlib.util.spec_from_file_location(
                "screen", Path(__file__).resolve().parents[1] / "projects" / "screen.py"
            )
            screen = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(screen)

            def fake_display_and_save(pil_images, frame_files, output_gif):
                durations_ms = [100] * len(pil_images)
                flat = [im.convert("RGB") for im in pil_images]
                flat[0].save(
                    output_gif,
                    save_all=True,
                    append_images=flat[1:],
                    duration=durations_ms,
                    loop=0,
                    disposal=1,
                    optimize=True,
                )
                return output_gif

            out_gif = tmp_path / "out.gif"
            with patch.object(screen, "_display_and_save", fake_display_and_save):
                screen.animate_gif(str(tmp_path), output_gif=str(out_gif))

            self.assertTrue(out_gif.exists())
            with Image.open(out_gif) as im:
                self.assertTrue(getattr(im, "n_frames", 1) > 1)


if __name__ == "__main__":
    unittest.main()
