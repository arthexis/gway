# file: tests/test_setup_app_fallback.py

import unittest
from gway import gw
from paste.fixture import TestApp

class SetupAppFallbackTests(unittest.TestCase):
    def test_first_available_project_is_loaded(self):
        app = gw.web.app.setup_app(["nope", "dummy"])
        client = TestApp(app)
        resp = client.get("/dummy")
        self.assertEqual(resp.status, 200)
        self.assertIn("Dummy Index", resp.body.decode())

if __name__ == "__main__":
    unittest.main()
