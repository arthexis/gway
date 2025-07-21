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
