import unittest
from unittest.mock import patch
from paste.fixture import TestApp
from gway import gw


class SitemapXMLTests(unittest.TestCase):
    def setUp(self):
        gw.results.clear()
        gw.context.clear()

    def test_sitemap_contains_registered_routes(self):
        app = gw.web.app.setup_app("dummy", home="index")
        gw.web.app.setup_app("web.sitemap", app=app)
        with patch.object(gw.web, "base_url", return_value="https://example.com"):
            client = TestApp(app)
            resp = client.get("/sitemap.xml")
            body = resp.body.decode()
            self.assertIn("<loc>https://example.com/dummy/index</loc>", body)
            self.assertIn("<loc>https://example.com/dummy/about</loc>", body)


if __name__ == "__main__":
    unittest.main()
