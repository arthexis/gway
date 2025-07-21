import unittest
from gway import gw
from paste.fixture import TestApp

class GatewayCookbookLinkTests(unittest.TestCase):
    def setUp(self):
        self.app = gw.web.app.setup_app("web.site")
        self.client = TestApp(self.app)

    def test_footer_link_points_to_cookbook(self):
        resp = self.client.get("/web/site/reader")
        body = resp.body.decode()
        self.assertIn("/web/site/gateway-cookbook", body)
        self.assertNotIn("/web/site/web/site/gateway-cookbook", body)

if __name__ == "__main__":
    unittest.main()
