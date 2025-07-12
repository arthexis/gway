import unittest
import sys
from gway import gw
from paste.fixture import TestApp

class SetupHomeLinksFuncTests(unittest.TestCase):
    def test_defaults_from_project_functions(self):
        app = gw.web.app.setup_app("dummy")
        mod = sys.modules[gw.web.app.setup_app.__module__]
        self.assertIn(("Dummy", "dummy/index"), mod._homes)
        self.assertEqual(mod._links.get("dummy/index"), ["about", "more"])
        client = TestApp(app)
        resp = client.get("/dummy")
        self.assertEqual(resp.status, 200)
        self.assertIn("Dummy Index", resp.body.decode())

if __name__ == "__main__":
    unittest.main()
