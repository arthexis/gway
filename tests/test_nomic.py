import importlib.util
import unittest
from gway import gw


class NomicTests(unittest.TestCase):
    def setUp(self):
        path = gw.resource('projects', 'games', 'nomic.py')
        spec = importlib.util.spec_from_file_location('nomic_mod', str(path))
        self.nomic_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.nomic_mod)

    def test_view_has_sections(self):
        html = self.nomic_mod.view_nomic()
        self.assertIn('Hypernomic', html)
        self.assertIn('Rules', html)
        self.assertIn('Proposals', html)
        self.assertIn('Scores', html)


if __name__ == '__main__':
    unittest.main()
