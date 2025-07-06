import unittest
import importlib.util
from pathlib import Path
from unittest.mock import patch
from bs4 import BeautifulSoup

app_path = Path(__file__).resolve().parents[1] / "projects" / "web" / "app.py"
spec = importlib.util.spec_from_file_location("webapp", app_path)
webapp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(webapp)

class RenderTemplateThemeCssTests(unittest.TestCase):
    def test_base_and_theme_css_links(self):
        dummy_theme = "/static/theme.css"
        with patch.object(webapp.gw.web.nav, 'active_style', return_value=dummy_theme), \
             patch.object(webapp.gw.web.nav, 'render', return_value=''), \
             patch.object(webapp, 'is_setup', return_value=True):
            html = webapp.render_template(css_files=['/static/base.css'])

        soup = BeautifulSoup(html, 'html.parser')
        links = [l['href'] for l in soup.find_all('link', rel='stylesheet')]
        self.assertEqual(links, ['/static/base.css', dummy_theme])

if __name__ == '__main__':
    unittest.main()
