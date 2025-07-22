import unittest
from unittest.mock import patch
from gway import gw

class FakeRequest:
    def __init__(self):
        self.fullpath = '/web/site/index'
        self.query = {}
        self.query_string = ''
        self.environ = {}
    def get_header(self, name):
        return None

class NavTopTests(unittest.TestCase):
    def test_render_top_nav(self):
        old_side = gw.web.nav.side()
        try:
            gw.web.nav.setup_app(side='top')
            with patch('web_nav.request', FakeRequest()):
                html = gw.web.nav.render(homes=[('Home', 'web/site')],
                                          links={'web/site': ['about']})
            self.assertIn('<nav', html)
            self.assertIn('sub-links', html)
            self.assertIn('top-bar', html)
        finally:
            gw.web.nav.setup_app(side=old_side)

    def test_skeleton_recipe_sets_nav_top(self):
        from gway.console import load_recipe, process
        import sys

        # Ensure nav module is loaded and store state for restoration
        _ = gw.web.nav.side()
        old_module = sys.modules['web_nav']
        old_side = old_module._side
        old_cache = gw._cache.get('web.nav')

        try:
            cmds, _ = load_recipe('skeleton.gwr')
            with patch.object(gw.web.server, 'start_app'), \
                 patch.object(gw, 'until'), \
                 patch.object(gw.web.static, 'collect'), \
                 patch.object(gw.help_db, 'build'):
                process(cmds)

            nav_mod = sys.modules['web_nav']
            self.assertEqual(nav_mod._side, 'top')
            with patch.object(nav_mod, 'request', FakeRequest()):
                html = nav_mod.render(homes=[('Home', 'web/site')],
                                      links={'web/site': ['about']})
            self.assertIn('<nav', html)
            self.assertIn('top-bar', html)
            self.assertNotIn('<aside', html)
        finally:
            sys.modules['web_nav'] = old_module
            old_module._side = old_side
            gw._cache['web.nav'] = old_cache

if __name__ == '__main__':
    unittest.main()

