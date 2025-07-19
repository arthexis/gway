import unittest
import sys
from gway import gw
from paste.fixture import TestApp

class FooterLinksTests(unittest.TestCase):
    def setUp(self):
        gw.results.clear()
        gw.context.clear()

    def tearDown(self):
        gw.results.clear()
        gw.context.clear()

    def test_footer_links_render(self):
        app = gw.web.app.setup_app("dummy", footer="info")
        mod = sys.modules[gw.web.app.setup_app.__module__]
        self.assertEqual(mod._footer_links.get("dummy/index"), ["info"])
        client = TestApp(app)
        resp = client.get("/dummy")
        self.assertEqual(resp.status, 200)
        body = resp.body.decode()
        self.assertIn('<p class="footer-links">', body)
        self.assertIn('/dummy/info', body)

if __name__ == "__main__":
    unittest.main()
