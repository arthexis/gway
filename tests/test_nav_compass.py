import importlib.util
from pathlib import Path
import unittest
from urllib.parse import parse_qs

from bs4 import BeautifulSoup

# Load nav.py dynamically
nav_path = Path(__file__).resolve().parents[1] / 'projects' / 'web' / 'nav.py'
spec = importlib.util.spec_from_file_location('webnav', nav_path)
nav = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nav)

class FakeRequest:
    def __init__(self, path, query=''):
        self.fullpath = path
        self.query_string = query
        params = dict(parse_qs(query, keep_blank_values=True))
        self.query = type('Q', (), {'get': lambda self2, k, d=None, p=params: p.get(k, [d])[0]})()

class NavCompassTests(unittest.TestCase):
    def setUp(self):
        self.orig_request = nav.request
        self.orig_app = nav.gw.web.app
        nav.gw.web.app = type('A', (), {'is_make': lambda self2, n: False})()
        self.orig_cookies = nav.gw.web.cookies
        nav.gw.web.cookies = type('C', (), {'accepted': lambda self2: False})()
        self.orig_qr = nav.gw.qr.generate_url
        nav.gw.qr.generate_url = lambda url: '/qr/generated'
        self.orig_project = getattr(nav.gw, 'myproj', None)
        nav.gw.myproj = type('P', (), {'view_compass': lambda self2=None: '<div>LOCAL</div>'})()

    def tearDown(self):
        nav.request = self.orig_request
        nav.gw.web.app = self.orig_app
        nav.gw.web.cookies = self.orig_cookies
        nav.gw.qr.generate_url = self.orig_qr
        if self.orig_project is not None:
            nav.gw.myproj = self.orig_project
        else:
            delattr(nav.gw, 'myproj')

    def test_default_uses_local_compass(self):
        nav.request = FakeRequest('/myproj/view')
        html = nav.render()
        self.assertIn('<div>LOCAL</div>', html)
        self.assertIn('Show QR to Here', html)
        self.assertNotIn('/qr/generated', html)

    def test_qr_mode(self):
        nav.request = FakeRequest('/myproj/view', 'compass=qr')
        html = nav.render()
        soup = BeautifulSoup(html, 'html.parser')
        img = soup.find('img', {'class': 'compass'})
        self.assertIsNotNone(img)
        self.assertEqual(img['src'], '/qr/generated')
        self.assertIn('Show local compass', html)

    def test_no_toggle_without_view_compass(self):
        delattr(nav.gw.myproj.__class__, 'view_compass')
        nav.request = FakeRequest('/myproj/view')
        html = nav.render()
        self.assertIn('/qr/generated', html)
        self.assertNotIn('Show QR to Here', html)
        self.assertNotIn('Show local compass', html)

if __name__ == '__main__':
    unittest.main()
