import importlib.util
from pathlib import Path
import unittest
from bs4 import BeautifulSoup

class FakeRequest:
    def __init__(self, path):
        self.fullpath = path
        self.query = type('Q', (), {'get': lambda self2, k, d=None: d})()
        self.query_string = ''

class NavLinksTests(unittest.TestCase):
    @staticmethod
    def _load_nav():
        nav_path = Path(__file__).resolve().parents[1] / 'projects' / 'web' / 'nav.py'
        spec = importlib.util.spec_from_file_location('webnav', nav_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    @classmethod
    def setUpClass(cls):
        global nav
        nav = cls._load_nav()
    def setUp(self):
        self.orig_request = nav.request
        nav.request = FakeRequest('/games/game-of-life')
        self.orig_app = nav.gw.web.app
        nav.gw.web.app = type('A', (), {'is_setup': lambda self2, n: False})()
        self.orig_cookies = nav.gw.web.cookies
        nav.gw.web.cookies = type('C', (), {'accepted': lambda self2: False})()

    def tearDown(self):
        nav.request = self.orig_request
        nav.gw.web.app = self.orig_app
        nav.gw.web.cookies = self.orig_cookies

    def test_render_includes_project_links(self):
        homes = [('Toys & Games', 'games/game-of-life')]
        html = nav.render(homes=homes, links={'games/game-of-life': ['score', 'about']})
        soup = BeautifulSoup(html, 'html.parser')
        sub = soup.find('ul', class_='sub-links')
        self.assertIsNotNone(sub)
        hrefs = [a['href'] for a in sub.find_all('a')]
        self.assertIn('/games/score', hrefs)
        self.assertIn('/games/about', hrefs)

    def test_sub_link_highlight_and_no_current_page(self):
        nav.gw.web.cookies = type('C', (), {'accepted': lambda self2: True,
                                             'get': lambda self2, n, d=None: None})()
        nav.gw.web.app = type('A', (), {'is_setup': lambda self2, n: True})()
        nav.request = FakeRequest('/games/score')
        homes = [('Toys & Games', 'games/game-of-life')]
        html = nav.render(homes=homes, links={'games/game-of-life': ['score', 'about']})
        soup = BeautifulSoup(html, 'html.parser')
        score_links = soup.find_all('a', href='/games/score')
        self.assertEqual(len(score_links), 1)
        self.assertIn('current', score_links[0].get('class', []))

    def test_current_page_not_added_when_missing(self):
        nav.gw.web.cookies = type('C', (), {'accepted': lambda self2: True,
                                             'get': lambda self2, n, d=None: None})()
        nav.gw.web.app = type('A', (), {'is_setup': lambda self2, n: True})()
        nav.request = FakeRequest('/unlisted/page')
        homes = [('Toys & Games', 'games/game-of-life')]
        html = nav.render(homes=homes)
        self.assertNotIn('/unlisted/page', html)

if __name__ == '__main__':
    unittest.main()
