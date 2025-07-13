import unittest
import importlib.util
from gway import gw


class QPigFarmTests(unittest.TestCase):
    def setUp(self):
        path = gw.resource('projects', 'games', 'qpig.py')
        spec = importlib.util.spec_from_file_location('qpig_mod', str(path))
        self.qpig_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.qpig_mod)

    def test_view_contains_canvas_and_buttons(self):
        html = self.qpig_mod.view_qpig_farm()
        self.assertIn('qpig-canvas', html)
        self.assertIn('qpig-save', html)
        self.assertIn('qpig-load', html)

    def test_tab_names_updated(self):
        html = self.qpig_mod.view_qpig_farm()
        self.assertIn('Garden Shed', html)
        self.assertIn('Market Street', html)
        self.assertIn('Laboratory', html)
        self.assertIn('Travel Abroad', html)


if __name__ == '__main__':
    unittest.main()
