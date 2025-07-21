import unittest
from gway import gw
from paste.fixture import TestApp

class GatewayCookbookLinkTests(unittest.TestCase):
    def setUp(self):
        gw.results.clear()
        gw.context.clear()

    def test_footer_link_not_included_by_default(self):
        app = gw.web.app.setup_app("web.site")
        client = TestApp(app)
        resp = client.get("/web/site/reader")
        body = resp.body.decode()
        self.assertNotIn("/web/site/gateway-cookbook", body)

    def test_footer_link_added_via_option(self):
        app = gw.web.app.setup_app("web.site", footer="gateway-cookbook")
        client = TestApp(app)
        resp = client.get("/web/site/reader")
        body = resp.body.decode()
        self.assertIn("/web/site/gateway-cookbook", body)

if __name__ == "__main__":
    unittest.main()
