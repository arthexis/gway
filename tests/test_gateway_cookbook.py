import unittest
from gway import gw
from paste.fixture import TestApp

class GatewayCookbookTests(unittest.TestCase):
    def test_listing_includes_recipe(self):
        html = gw.web.site.view_gateway_cookbook()
        self.assertIn('Midblog', html)
        self.assertIn('Gateway Cookbook', html)

    def test_recipe_view_renders(self):
        html = gw.web.site.view_gateway_cookbook(recipe='midblog.gwr')
        self.assertIn('midblog.gwr', html)
        self.assertIn('# file:', html)

    def test_nested_recipe_link_in_listing(self):
        app = gw.web.app.setup_app("web.site", footer="gateway-cookbook", home="reader")
        client = TestApp(app)
        resp = client.get("/web/site/gateway-cookbook")
        body = resp.body.decode()
        self.assertIn(
            "/web/site/gateway-cookbook?recipe=etron%2Flocal.gwr",
            body,
        )

if __name__ == '__main__':
    unittest.main()

