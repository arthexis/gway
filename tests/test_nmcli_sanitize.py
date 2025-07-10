import unittest
from pathlib import Path
import importlib.util

class SanitizeHelperTests(unittest.TestCase):
    @staticmethod
    def _load_nmcli():
        nmcli_path = Path(__file__).resolve().parents[1] / 'projects' / 'monitor' / 'nmcli.py'
        spec = importlib.util.spec_from_file_location('nmcli_mod', nmcli_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    @classmethod
    def setUpClass(cls):
        cls.nmcli_mod = cls._load_nmcli()
    def test_sanitize_quotes(self):
        self.assertEqual(self.nmcli_mod._sanitize('"foo"'), 'foo')


if __name__ == '__main__':
    unittest.main()
