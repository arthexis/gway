import unittest
import json
from gway import gw
import unittest.mock as mock
import importlib.util


class QPigFarmButtonTests(unittest.TestCase):
    def setUp(self):
        self.time_patch = mock.patch('time.time', lambda: 0)
        self.time_patch.start()
        # Load the underlying module for constants
        path = gw.resource('projects', 'games', 'qpig.py')
        spec = importlib.util.spec_from_file_location('qpig_mod', str(path))
        self.qpig_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.qpig_mod)

    def tearDown(self):
        self.time_patch.stop()

    def test_buy_small_and_adopt(self):
        state = {
            'pigs': self.qpig_mod.DEFAULT_PIGS,
            'mc': 1000.0,
            'pellets': 0.0,
            'time': 0.0,
            'avail': self.qpig_mod.DEFAULT_AVAILABLE,
            'enc_small': self.qpig_mod.DEFAULT_ENC_SMALL,
            'enc_large': self.qpig_mod.DEFAULT_ENC_LARGE,
            'last_add': 0.0,
            'veggies': {},
            'food': [],
            'offer': {'kind': 'carrot', 'qty': 1, 'price': 10, 'time': 0.0},
        }
        state = self.qpig_mod._process_state(state, 'buy_small')
        self.assertEqual(state['enc_small'], 2)
        self.assertEqual(state['mc'], 1000 - self.qpig_mod.SMALL_COST)

        state = self.qpig_mod._process_state(state, 'adopt')
        self.assertEqual(state['pigs'], 2)
        self.assertEqual(state['avail'], self.qpig_mod.DEFAULT_AVAILABLE - 1)

    def test_buy_and_place_veggie(self):
        state = {
            'pigs': self.qpig_mod.DEFAULT_PIGS,
            'mc': 1000.0,
            'pellets': 0.0,
            'time': 0.0,
            'avail': self.qpig_mod.DEFAULT_AVAILABLE,
            'enc_small': self.qpig_mod.DEFAULT_ENC_SMALL,
            'enc_large': self.qpig_mod.DEFAULT_ENC_LARGE,
            'last_add': 0.0,
            'veggies': {},
            'food': [],
            'offer': {'kind': 'carrot', 'qty': 2, 'price': 10, 'time': 0.0},
        }
        state = self.qpig_mod._process_state(state, 'buy_veggie')
        self.assertEqual(state['veggies'].get('carrot'), 2)
        self.assertEqual(state['mc'], 1000 - 20)

        state = self.qpig_mod._process_state(state, 'place_carrot')
        self.assertEqual(state['veggies'].get('carrot'), 1)
        self.assertEqual(len(state['food']), 1)
        self.assertEqual(state['food'][0][0], 'carrot')

    def test_view_contains_canvas(self):
        html = self.qpig_mod.view_qpig_farm()
        self.assertIn("qpig-canvas", html)

if __name__ == '__main__':
    unittest.main()
