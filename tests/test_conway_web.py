# file: tests/test_conway_web.py




import unittest
import subprocess
import time
import socket
import sys
import requests
from bs4 import BeautifulSoup
from gway import gw
from gway.builtins import is_test_flag

class ConwayWebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Start the demo website (port 8888)
        cls.proc = subprocess.Popen(
            [sys.executable, "-m", "gway", "-r", "test/website"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        cls._wait_for_port(18888, timeout=15)
        # Give server time to finish startup
        time.sleep(2)
        cls.base_url = "http://127.0.0.1:18888"

    @classmethod
    def tearDownClass(cls):
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
                with socket.create_connection(("127.0.0.1", port), timeout=1):
                    return
            except OSError:
                time.sleep(0.2)
        raise TimeoutError(f"Port {port} not responding after {timeout} seconds")

    def _get_soup(self, url):
        resp = requests.get(url)
        self.assertEqual(
            resp.status_code, 200,
            f"Non-200 status code: {resp.status_code}\nURL: {url}"
        )
        return BeautifulSoup(resp.text, "html.parser"), resp

    def test_game_of_life_page_includes_css_and_js(self):
        """Game of Life page includes its css/js and download link."""
        soup, resp = self._get_soup(self.base_url + "/games/game-of-life")
        # CSS
        css_links = [link['href'] for link in soup.find_all('link', rel="stylesheet")]
        gw.info(f"CSS links found: {css_links}")
        self.assertIn("/shared/global.css", css_links, f"/shared/global.css not in {css_links}")
        # JS
        js_links = [script['src'] for script in soup.find_all('script', src=True)]
        gw.info(f"JS scripts found: {js_links}")
        self.assertIn("/shared/global.js", js_links, f"/shared/global.js not in {js_links}")
        # Download link
        download_link = soup.find('a', href="/shared/games/conway.txt")
        self.assertIsNotNone(download_link, "Download link for /shared/games/conway.txt not found in page HTML")
        # Optionally: log the first part of the page for debugging
        gw.info("Top of page: " + str(soup)[:400])

    def test_game_of_life_css_file_downloadable(self):
        """CSS bundle is downloadable with correct content type."""
        url = self.base_url + "/shared/global.css"
        resp = requests.get(url)
        self.assertEqual(
            resp.status_code, 200,
            f"CSS not found (status {resp.status_code})."
        )
        self.assertIn(
            "text/css", resp.headers.get("Content-Type", ""),
            f"Wrong content-type for CSS: {resp.headers.get('Content-Type')}"
        )
        self.assertTrue(
            len(resp.text) > 0,
            "CSS file is empty!"
        )

    def test_game_of_life_js_file_downloadable(self):
        """JS bundle is downloadable with correct content type."""
        url = self.base_url + "/shared/global.js"
        resp = requests.get(url)
        self.assertEqual(
            resp.status_code, 200,
            f"JS not found (status {resp.status_code})."
        )
        content_type = resp.headers.get("Content-Type", "")
        self.assertTrue(
            "javascript" in content_type.lower(),
            f"Wrong content-type for JS: {content_type}"
        )
        self.assertTrue(
            len(resp.text) > 0,
            "JS file is empty!"
        )

    def test_download_board_link_works(self):
        """/shared/games/conway.txt returns a plain text file, not HTML, and is not empty."""
        path = "/shared/games/conway.txt"
        # load_board will create the board if missing, avoiding the missing file error
        gw.games.conway.save_board(gw.games.conway.load_board())
        url = self.base_url + path
        resp = requests.get(url)
        self.assertEqual(
            resp.status_code, 200,
            f"/shared/games/conway.txt not found (status {resp.status_code})."
        )
        self.assertIn(
            "text/plain", resp.headers.get("Content-Type", ""),
            f"Wrong content-type for board file: {resp.headers.get('Content-Type')}"
        )
        self.assertIn(
            ",", resp.text,
            "Board file does not contain CSV (no commas found)."
        )
        self.assertIn(
            "\n", resp.text,
            "Board file does not contain newlines."
        )

    def test_css_and_js_are_linked_first(self):
        """
        CSS should appear in <head>, JS should appear before </body>.
        """
        soup, resp = self._get_soup(self.base_url + "/games/game-of-life")
        head = soup.head
        body = soup.body
        # CSS in head
        css_links = [link['href'] for link in head.find_all('link', rel="stylesheet")]
        self.assertIn("/shared/global.css", css_links, f"/shared/global.css not linked in <head>: {css_links}")
        # JS at bottom of body (look for the last scripts)
        js_links = [script['src'] for script in body.find_all('script', src=True)]
        self.assertIn("/shared/global.js", js_links, f"/shared/global.js not linked before </body>: {js_links}")

    @unittest.skipUnless(is_test_flag("screen"), "Screen tests disabled")
    def test_conway_game_page_screenshot(self):
        """Capture a screenshot of the Game of Life page for manual review."""
        screenshot_dir = Path("work/screenshots")
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        screenshot_file = screenshot_dir / "conway_game.png"
        try:
            gw.web.auto.capture_page_source(
                self.base_url + "/games/game-of-life",
                screenshot=str(screenshot_file),
            )
        except Exception as e:
            self.skipTest(f"Webdriver unavailable: {e}")
        self.assertTrue(screenshot_file.exists())

if __name__ == "__main__":
    unittest.main()
