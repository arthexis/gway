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

    def test_project_readmes_links_have_no_double_prefix(self):
        resp = self.client.get("/web/site/project-readmes")
        body = resp.body.decode()
        self.assertIn("/web/site/reader", body)
        self.assertNotIn("/web/site/web/site/reader", body)

    def test_cookbook_listing_links_have_no_double_prefix(self):
        resp = self.client.get("/web/site/gateway-cookbook")
        body = resp.body.decode()
        self.assertIn("/web/site/gateway-cookbook", body)
        self.assertNotIn("/web/site/web/site/gateway-cookbook", body)

    def test_pending_todos_help_links_have_no_double_prefix(self):
        gw.help_db.build(update=True)
        resp = self.client.get("/web/site/pending-todos")
        body = resp.body.decode()
        self.assertIn("/web/site/help", body)
        self.assertNotIn("/web/site/web/site/help", body)

if __name__ == "__main__":
    unittest.main()
