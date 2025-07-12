import unittest
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch, MagicMock
import types

import numpy as np

from gway import gw


class MicRecordTests(unittest.TestCase):
    @staticmethod
    def _load_mic():
        mic_path = Path(__file__).resolve().parents[1] / "projects" / "mic.py"
        spec = importlib.util.spec_from_file_location("mic", mic_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_record_returns_path(self):
        mic = self._load_mic()
        fake_data = np.zeros((1, 1), dtype="int16")
        with TemporaryDirectory() as tmpdir:
            def fake_resource(*parts):
                return Path(tmpdir).joinpath(*parts)

            fake_wave = MagicMock()
            fake_wave.__enter__.return_value = MagicMock()

            fake_sd = types.SimpleNamespace(rec=MagicMock(return_value=fake_data), wait=MagicMock())
            with patch.dict('sys.modules', {'sounddevice': fake_sd}), \
                 patch.object(mic, 'wave') as wave_mod, \
                 patch.object(gw, 'resource', fake_resource):
                wave_mod.open.return_value = fake_wave
                result = mic.record(duration=1)

        self.assertTrue(Path(result).exists() or result.startswith(str(Path(tmpdir))))


if __name__ == "__main__":
    unittest.main()



