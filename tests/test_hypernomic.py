import importlib.util
import unittest
from gway import gw


class HypernomicTests(unittest.TestCase):
    def setUp(self):
        path = gw.resource('projects', 'games', 'hypernomic.py')
        spec = importlib.util.spec_from_file_location('hyper_mod', str(path))
        self.hyper_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.hyper_mod)

    def test_view_has_sections(self):
        html = self.hyper_mod.view_hypernomic()
        self.assertIn('Hypernomic', html)
        self.assertIn('Rules', html)
        self.assertIn('Proposals', html)
        self.assertIn('Scores', html)


if __name__ == '__main__':
    unittest.main()
