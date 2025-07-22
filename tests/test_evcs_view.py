import unittest
from gway import gw
from paste.fixture import TestApp
from unittest.mock import patch
from importlib import import_module

class EvcsViewTests(unittest.TestCase):
    def setUp(self):
        app = gw.web.app.setup('ocpp', everything=True)
        self.client = TestApp(app)

    def test_cp_simulator_view_renders(self):
        resp = self.client.get('/ocpp/evcs/cp-simulator')
        self.assertEqual(resp.status, 200)
        text = resp.body.decode()
        self.assertIn('<h1>OCPP Charge Point Simulator</h1>', text)

    def test_cp_simulator_start_action(self):
        """Starting the simulator via POST should call _start_simulator."""
        # Ensure the module is loaded so patching succeeds
        import_module('ocpp_evcs')
        with patch('ocpp_evcs._start_simulator', return_value=True) as start:
            resp = self.client.post('/ocpp/evcs/cp-simulator', {
                'cp': '1',
                'action': 'start',
            })
        self.assertEqual(resp.status, 200)
        text = resp.body.decode()
        self.assertIn('CP1 started.', text)
        start.assert_called_once()

if __name__ == '__main__':
    unittest.main()
