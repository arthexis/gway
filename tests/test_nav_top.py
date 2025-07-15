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

if __name__ == '__main__':
    unittest.main()

