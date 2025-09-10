import unittest
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch, MagicMock
import types
import sys

import numpy as np

from gway import gw


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
        fake_data = np.zeros((1, 1), dtype="int16")
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
                result = audio.record(duration=1)

        self.assertTrue(result.startswith(tmpdir))


if __name__ == "__main__":
    unittest.main()
