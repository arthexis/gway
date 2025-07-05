# file: tests/test_nav_styles.py

import unittest
import subprocess
import time
import socket
import requests
from bs4 import BeautifulSoup
import importlib.util
from pathlib import Path

# Dynamically load the web.auto helpers for screenshot capture
auto_path = Path(__file__).resolve().parents[1] / "projects" / "web" / "auto.py"
spec = importlib.util.spec_from_file_location("webauto", auto_path)
webauto = importlib.util.module_from_spec(spec)
spec.loader.exec_module(webauto)

class NavStyleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Launch the website recipe on a test port (8888)
        cls.proc = subprocess.Popen(
            ["gway", "-r", "test/website"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        cls._wait_for_port(18888, timeout=15)
        # Let the server warm up
        time.sleep(2)
        cls.base_url = "http://127.0.0.1:18888"

    @classmethod
    def tearDownClass(cls):
        # Cleanly terminate the test server process
        if hasattr(cls, "proc") and cls.proc:
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.proc.kill()

    @staticmethod
    def _wait_for_port(port, timeout=12):
        start = time.time()
        while time.time() - start < timeout:
            try:
                with socket.create_connection(("localhost", port), timeout=1):
                    return
            except OSError:
                time.sleep(0.2)
        raise TimeoutError(f"Port {port} not responding after {timeout} seconds")

    def _get_soup(self, url, session=None):
        if session:
            resp = session.get(url)
        else:
            resp = requests.get(url)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser"), resp

    def test_one_theme_css_link_in_head(self):
        """Ensure exactly one active theme CSS link in <head> and it's the correct one."""
        soup, _ = self._get_soup(self.base_url + "/nav/style-switcher?css=dark-material.css")
        head = soup.head
        theme_links = [link for link in head.find_all('link', rel="stylesheet") if "styles" in link.get('href', '')]
        self.assertEqual(
            len(theme_links), 1,
            f"Expected one active theme CSS in <head>, found: {[l['href'] for l in theme_links]}"
        )
        self.assertIn(
            "dark-material.css", theme_links[0]['href'],
            f"Expected 'dark-material.css' in theme link href, got {theme_links[0]['href']}"
        )

    def test_style_switcher_preview_injects_theme(self):
        """Style preview must inject the selected theme as a <link> for preview."""
        soup, _ = self._get_soup(self.base_url + "/nav/style-switcher?css=palimpsesto.css")
        preview_links = [link for link in soup.find_all('link', rel="stylesheet") if "palimpsesto.css" in link.get('href', '')]
        self.assertTrue(preview_links, "Preview theme link for palimpsesto.css not found.")
        preview_div = soup.find('div', class_="style-preview")
        self.assertIsNotNone(preview_div, "style-preview div not found")
        self.assertIn("Palimpsesto", preview_div.text, "Preview does not mention 'Palimpsesto'")

    # TODO: The following test keeps failing. We should do a standalone test for cookies to isolate the source

    def test_theme_switch_sets_css_cookie_and_main_link(self):
        """Test POST to change theme sets cookie and updates <head> <link>."""
        session = requests.Session()
        # Accept cookies
        session.post(self.base_url + "/cookies/accept")
        # POST to set theme to classic-95.css
        resp = session.post(
            self.base_url + "/nav/style-switcher",
            data={"css": "classic-95.css"},
            allow_redirects=True
        )
        # Check that the css cookie is set
        self.assertIn(
            "classic-95.css", session.cookies.get_dict().get("css", ""),
            f"Theme change did not set css cookie, got cookies: {session.cookies.get_dict()}"
        )
        # Now reload style-switcher and check <head>
        soup, _ = self._get_soup(self.base_url + "/nav/style-switcher", session)
        head = soup.head
        links = [l for l in head.find_all('link', rel="stylesheet") if "classic-95.css" in l.get('href', '')]
        self.assertTrue(links, "Theme change did not update main <link> to classic-95.css")

    def test_sidebar_has_no_theme_link(self):
        """Sidebar should NOT contain a <link> for the current theme."""
        resp = requests.get(self.base_url + "/nav/style-switcher")
        soup = BeautifulSoup(resp.text, "html.parser")
        aside = soup.find("aside")
        links = aside.find_all("link", rel="stylesheet") if aside else []
        # None of these should have id="nav-style-link" or match a theme
        self.assertTrue(
            all("nav-style-link" not in l.attrs.get("id", "") for l in links),
            f"Sidebar should NOT have theme <link> (found: {[str(l) for l in links]})"
        )

    def test_theme_cookie_and_css_link_on_other_page(self):
        """
        After accepting cookies and switching theme, the css cookie is set and a subsequent page
        includes the expected theme <link> in <head>.
        """
        session = requests.Session()
        # 1. Accept cookies (must be a POST)
        resp = session.post(self.base_url + "/cookies/accept")
        self.assertIn(
            "cookies_accepted", session.cookies.get_dict(),
            f"Did not set cookies_accepted cookie: {session.cookies.get_dict()}"
        )
        # 2. Visit style switcher and pick a theme
        resp = session.get(self.base_url + "/nav/style-switcher")
        soup = BeautifulSoup(resp.text, "html.parser")
        select = soup.find("select", id="css-style")
        assert select, "Could not find theme selector"
        options = [o['value'] for o in select.find_all("option")]
        assert "classic-95.css" in options, f"classic-95.css not in options: {options}"

        # 3. POST to switch theme
        resp = session.post(
            self.base_url + "/nav/style-switcher",
            data={"css": "classic-95.css"},
            allow_redirects=True
        )
        self.assertIn(
            "classic-95.css", session.cookies.get_dict().get("css", ""),
            f"Theme change did not set css cookie, got cookies: {session.cookies.get_dict()}"
        )

        # 4. Now visit /site/reader (or any other page)
        resp2 = session.get(self.base_url + "/site/reader")
        soup2 = BeautifulSoup(resp2.text, "html.parser")
        link = soup2.find("link", rel="stylesheet", href=lambda h: h and "classic-95.css" in h)
        self.assertIsNotNone(
            link,
            f"Readme page did not include expected theme <link> for classic-95.css in <head>. Got links: {[str(l) for l in soup2.find_all('link', rel='stylesheet')]}"
        )

    def test_style_switcher_screenshot(self):
        """Capture a screenshot of the style switcher page."""
        screenshot_dir = Path("work/screenshots")
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        screenshot_file = screenshot_dir / "style_switcher.png"
        try:
            webauto.capture_page_source(
                self.base_url + "/nav/style-switcher",
                screenshot=str(screenshot_file),
            )
        except Exception as e:
            self.skipTest(f"Webdriver unavailable: {e}")
        self.assertTrue(screenshot_file.exists())


if __name__ == "__main__":
    unittest.main()
