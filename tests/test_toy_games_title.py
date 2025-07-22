import importlib.util
from pathlib import Path
import unittest

from gway import gw


class ToyGamesTitleTests(unittest.TestCase):
    def test_func_title_resolves(self):
        nav_path = Path(__file__).resolve().parents[1] / 'projects' / 'web' / 'nav.py'
        spec = importlib.util.spec_from_file_location('webnav', nav_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        title = module._func_title('games', 'toy-games')
        self.assertEqual(title, 'Toys & Games')


if __name__ == '__main__':
    unittest.main()
