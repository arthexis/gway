import unittest
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock
import types
import numpy as np

from gway import gw


def _load_video():
    video_path = Path(__file__).resolve().parents[1] / "projects" / "studio" / "video.py"
    spec = importlib.util.spec_from_file_location("video", video_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CaptureCameraTests(unittest.TestCase):
    def test_capture_camera_yields_frames_and_releases(self):
        video = _load_video()
        frame = np.zeros((10, 10, 3), dtype="uint8")

        fake_cap = MagicMock()
        fake_cap.isOpened.return_value = True
        fake_cap.read.side_effect = [(True, frame), (False, None)]
        fake_cv2 = types.SimpleNamespace(VideoCapture=MagicMock(return_value=fake_cap))

        with unittest.mock.patch.dict('sys.modules', {'cv2': fake_cv2}):
            gen = video.capture_camera(source=0)
            frames = list(gen)

        self.assertEqual(len(frames), 1)
        fake_cap.release.assert_called_once()


class DisplayVideoTests(unittest.TestCase):
    def test_display_video_rejects_non_iterable(self):
        video = _load_video()
        with self.assertRaises(ValueError):
            video.display_video(123)

    def test_display_video_consumes_stream(self):
        video = _load_video()
        frames = [np.zeros((5, 5, 3), dtype="uint8") for _ in range(2)]
        stream = (f for f in frames)

        fake_display = MagicMock()
        fake_display.set_mode.return_value = MagicMock()
        fake_pygame = types.SimpleNamespace(
            init=MagicMock(),
            quit=MagicMock(),
            display=fake_display,
            surfarray=types.SimpleNamespace(make_surface=MagicMock(return_value=MagicMock())),
            event=types.SimpleNamespace(get=MagicMock(return_value=[])),
            QUIT=1,
        )
        fake_cv2 = types.SimpleNamespace(colorConverter=MagicMock(), COLOR_BGR2RGB=0, cvtColor=lambda f, code: f)

        with unittest.mock.patch.dict('sys.modules', {'pygame': fake_pygame, 'cv2': fake_cv2}):
            result = video.display_video(stream)

        self.assertTrue(result)
        fake_display.set_mode.assert_called_once()
        fake_pygame.quit.assert_called_once()


if __name__ == '__main__':
    unittest.main()
