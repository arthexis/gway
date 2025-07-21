import unittest
from gway import gw

class GatewayCookbookTests(unittest.TestCase):
    def test_listing_includes_recipe(self):
        html = gw.web.site.view_gateway_cookbook()
        self.assertIn('Micro Blog', html)
        self.assertIn('Gateway Cookbook', html)

    def test_recipe_view_renders(self):
        html = gw.web.site.view_gateway_cookbook(recipe='micro_blog.gwr')
        self.assertIn('micro_blog.gwr', html)
        self.assertIn('# file:', html)

if __name__ == '__main__':
    unittest.main()

