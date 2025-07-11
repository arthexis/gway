import unittest
import importlib.util
from pathlib import Path
from unittest.mock import patch, MagicMock

class RpiCloneTests(unittest.TestCase):
    @staticmethod
    def _load_rpi():
        rpi_path = Path(__file__).resolve().parents[1] / 'projects' / 'rpi.py'
        spec = importlib.util.spec_from_file_location('rpi', rpi_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    @classmethod
    def setUpClass(cls):
        cls.rpi = cls._load_rpi()

    def test_ru_invokes_dd(self):
        with patch.object(self.rpi.subprocess, 'run') as run_mock:
            run_mock.return_value = MagicMock(returncode=0, stdout='ok', stderr='')
            result = self.rpi.ru('/dev/test')
            run_mock.assert_called_with([
                'sudo', 'dd', 'if=/dev/mmcblk0', 'of=/dev/test', 'bs=4M',
                'status=progress', 'conv=fsync'
            ], capture_output=True, text=True)
            self.assertEqual(result, 'ok')

    def test_view_pi_remote_lists_devices(self):
        with patch.object(self.rpi, '_list_devices', return_value=['/dev/sda']), \
             patch.object(self.rpi.gw.web.app, 'render_template', lambda **kw: kw['content']):
            html = self.rpi.view_pi_remote()
        self.assertIn('/dev/sda', html)
        self.assertIn('clone-progress', html)

    def test_view_pi_remote_starts_clone(self):
        def fake_thread(target, args=(), daemon=None):
            class _T:
                def start(self):
                    target(*args)
            return _T()

        with patch.object(self.rpi, '_list_devices', return_value=['/dev/sda']), \
             patch.object(self.rpi.gw.web.app, 'render_template', lambda **kw: kw['content']), \
             patch.object(self.rpi, 'ru') as ru_mock, \
             patch.object(self.rpi.threading, 'Thread', side_effect=fake_thread):
            html = self.rpi.view_pi_remote(target='/dev/sda')
        ru_mock.assert_called_with('/dev/sda')
        self.assertIn('clone-progress', html)
        self.assertEqual(self.rpi._CLONE_STATE['progress'], 100.0)

if __name__ == '__main__':
    unittest.main()
