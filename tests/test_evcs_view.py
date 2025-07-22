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

if __name__ == '__main__':
    unittest.main()
