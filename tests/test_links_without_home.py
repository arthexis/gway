import unittest
import sys
from gway import gw
from paste.fixture import TestApp

class LinksWithoutHomeTests(unittest.TestCase):
    def setUp(self):
        gw.results.clear()
        gw.context.clear()

    def tearDown(self):
        gw.results.clear()
        gw.context.clear()

    def test_links_append_to_last_home(self):
        mod = sys.modules[gw.web.app.setup_app.__module__]
        mod._homes.clear()
        mod._links.clear()
        mod._registered_routes.clear()
        mod._enabled.clear()
        app = gw.web.app.setup_app("dummy", app=None)
        # Add an extra link without specifying home
        gw.web.app.setup_app("dummy", app=app, links="info")
        mod = sys.modules[gw.web.app.setup_app.__module__]
        self.assertEqual(mod._homes, [("Dummy", "dummy/index")])
        self.assertEqual(
            mod._links.get("dummy/index"),
            [("dummy", "about"), ("dummy", "more"), ("dummy", "info")],
        )
        client = TestApp(app)
        resp = client.get("/dummy")
        self.assertEqual(resp.status, 200)
        self.assertIn("Dummy Index", resp.body.decode())

if __name__ == "__main__":
    unittest.main()
