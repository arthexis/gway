import unittest
import importlib.util
from gway import gw


class QPigFarmTests(unittest.TestCase):
    def setUp(self):
        path = gw.resource('projects', 'games', 'qpig.py')
        spec = importlib.util.spec_from_file_location('qpig_mod', str(path))
        self.qpig_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.qpig_mod)

    def test_view_contains_basic_elements(self):
        html = self.qpig_mod.view_qpig_farm()
        self.assertNotIn("<canvas id='qpig-canvas'", html)
        self.assertIn('qpig-save', html)
        self.assertIn('qpig-load', html)
        self.assertIn('id="qpig-count"', html)
        self.assertIn('id="qpig-pellets"', html)
        self.assertIn('id="qpig-vcreds"', html)
        self.assertIn('qpig-pig-card', html)
        self.assertIn('market-stalls', html)
        self.assertIn('id="qpig-lab-pellets"', html)
        self.assertIn('id="qpig-lab-vcreds"', html)

    def test_tab_names_updated(self):
        html = self.qpig_mod.view_qpig_farm()
        self.assertIn('Garden Shed', html)
        self.assertIn('Market Street', html)
        self.assertIn('Quantum Lab', html)
        self.assertIn('Travel Abroad', html)
        self.assertIn('Game Settings', html)

    def test_lab_operations_table_present(self):
        html = self.qpig_mod.view_qpig_farm()
        self.assertIn('qpig-lab-ops', html)
        self.assertIn('Measure Spin', html)
        self.assertIn('Collect Quantum Pellets', html)


if __name__ == '__main__':
    unittest.main()
