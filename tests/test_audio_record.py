import unittest
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch, MagicMock
import types
import sys

import numpy as np

from gway import gw
from gway.builtins import is_test_flag


@unittest.skipUnless(
    is_test_flag("audio"),
    "Audio recording tests disabled (enable with --flags audio)",
)
class AudioRecordTests(unittest.TestCase):
    @staticmethod
    def _load_audio():
        audio_path = Path(__file__).resolve().parents[1] / "projects" / "audio.py"
        spec = importlib.util.spec_from_file_location("audio", audio_path)
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"sounddevice": types.SimpleNamespace()}):
            spec.loader.exec_module(module)
        return module

    def test_record_defaults_to_work_directory(self):
        audio = self._load_audio()
        fake_data = np.zeros((1, 1), dtype="float32")
        with TemporaryDirectory() as tmpdir:
            def fake_resource(*parts, **kwargs):
                return Path(tmpdir).joinpath(*parts)

            fake_wave = MagicMock()
            fake_wave.__enter__.return_value = MagicMock()

            fake_sd = types.SimpleNamespace(rec=MagicMock(return_value=fake_data), wait=MagicMock())
            with patch.object(gw, 'resource', fake_resource), \
                 patch.object(audio, 'sd', fake_sd), \
                 patch.object(audio, 'wave') as wave_mod:
                wave_mod.open.return_value = fake_wave
                result = audio.record(duration=1, immediate=True)

        self.assertTrue(result.startswith(tmpdir))


    def test_record_stores_result_and_playback_injects(self):
        audio = self._load_audio()
        fake_data = np.zeros((1, 1), dtype="float32")
        with TemporaryDirectory() as tmpdir:
            def fake_resource(*parts, **kwargs):
                return Path(tmpdir).joinpath(*parts)

            fake_wave = MagicMock()
            fake_wave.__enter__.return_value = MagicMock()

            fake_sd = types.SimpleNamespace(rec=MagicMock(return_value=fake_data), wait=MagicMock())
            with patch.object(gw, 'resource', fake_resource), \
                 patch.object(audio, 'sd', fake_sd), \
                 patch.object(audio, 'wave') as wave_mod:
                wave_mod.open.return_value = fake_wave
                record_wrapped = gw.wrap_callable("audio.record", audio.record)
                playback_wrapped = gw.wrap_callable("audio.playback", lambda *, audio: audio)
                gw.results.clear()
                path = record_wrapped(duration=1, immediate=True)
                self.assertEqual(gw.results.get('audio'), path)
                result = playback_wrapped()
                self.assertEqual(result, path)

    def test_sample_limits_duration(self):
        audio = self._load_audio()
        fake_data = np.zeros((441, 1), dtype="float32")
        with TemporaryDirectory() as tmpdir:
            def fake_resource(*parts, **kwargs):
                return Path(tmpdir).joinpath(*parts)

            fake_wave = MagicMock()
            fake_wave.__enter__.return_value = MagicMock()

            fake_sd = types.SimpleNamespace(rec=MagicMock(return_value=fake_data), wait=MagicMock())
            with patch.object(gw, 'resource', fake_resource), \
                 patch.object(audio, 'sd', fake_sd), \
                 patch.object(audio, 'wave') as wave_mod:
                wave_mod.open.return_value = fake_wave
                audio.record(duration=5, sample=0.01, immediate=True)

        expected_frames = int(round(min(5, 0.01) * 44100))
        fake_sd.rec.assert_called_once_with(expected_frames, samplerate=44100, channels=1)

    def test_stream_returns_audio_stream(self):
        audio = self._load_audio()
        fake_data = np.ones((22050, 2), dtype="float32") * 0.5
        with TemporaryDirectory() as tmpdir:
            def fake_resource(*parts, **kwargs):
                return Path(tmpdir).joinpath(*parts)

            fake_wave = MagicMock()
            fake_wave.__enter__.return_value = MagicMock()

            fake_sd = types.SimpleNamespace(rec=MagicMock(return_value=fake_data), wait=MagicMock())
            with patch.object(gw, 'resource', fake_resource), \
                 patch.object(audio, 'sd', fake_sd), \
                 patch.object(audio, 'wave') as wave_mod:
                wave_mod.open.return_value = fake_wave
                result = audio.record(duration=0.5, channels=2, immediate=True, stream=True)

        self.assertIsInstance(result, audio.AudioStream)
        np.testing.assert_array_equal(result.data, fake_data)
        self.assertEqual(result.samplerate, 44100)
        self.assertEqual(result.channels, 2)
        self.assertTrue(result.path.name.endswith(".wav"))


if __name__ == "__main__":
    unittest.main()
