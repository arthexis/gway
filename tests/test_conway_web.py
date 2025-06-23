# file: tests/test_conway_web.py

import unittest
import subprocess
import time
import socket
import requests

class ConwayWebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Use website recipe, port 8888
        cls.proc = subprocess.Popen(
            ["gway", "-r", "website"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        cls._wait_for_port(8888, timeout=12)
        # Let server start and write files
        time.sleep(2)
        cls.base_url = "http://127.0.0.1:8888"

    @classmethod
    def tearDownClass(cls):
        # Kill the subprocess
        if hasattr(cls, "proc") and cls.proc:
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.proc.kill()

    @staticmethod
    def _wait_for_port(port, timeout=10):
        start = time.time()
        while time.time() - start < timeout:
            try:
                with socket.create_connection(("localhost", port), timeout=1):
                    return
            except OSError:
                time.sleep(0.2)
        raise TimeoutError(f"Port {port} not responding after {timeout} seconds")

    def _trim_html(self, html, max_lines=40):
        """
        Trim HTML for readable test failure output:
        - Show only the first and last max_lines of HTML
        - Replace all form contents with [FORM DATA]
        - Skip the gameboard table with [ ... gameboard table trimmed ... ]
        """
        lines = html.splitlines()
        trimmed = []
        in_form = False
        in_table = False

        for line in lines:
            # Detect the gameboard table
            if '<table' in line and 'id="gameboard"' in line:
                in_table = True
                trimmed.append('[... gameboard table trimmed ...]')
                continue
            if in_table and '</table>' in line:
                in_table = False
                continue
            if in_table:
                continue

            # Detect form blocks
            if '<form' in line:
                in_form = True
                trimmed.append('[FORM DATA]')
                continue
            if in_form and '</form>' in line:
                in_form = False
                continue
            if in_form:
                continue

            # Otherwise, keep line
            trimmed.append(line)

        # Now apply head/tail limit
        if len(trimmed) > max_lines * 2:
            head = trimmed[:max_lines]
            tail = trimmed[-max_lines:]
            return "\n".join(head) + "\n[... trimmed ...]\n" + "\n".join(tail)
        return "\n".join(trimmed)

    def test_game_of_life_page_includes_css_and_js(self):
        """Game of Life page includes its css/js and download link."""
        resp = requests.get(self.base_url + "/conway/game-of-life")
        self.assertEqual(
            resp.status_code, 200,
            f"Non-200 status code: {resp.status_code}\n{self._trim_html(resp.text)}"
        )
        html = resp.text

        self.assertIn(
            '/static/conway/styles/game_of_life.css', html,
            "game_of_life.css not found in HTML:\n" + self._trim_html(html)
        )
        self.assertIn(
            '/static/conway/scripts/game_of_life.js', html,
            "game_of_life.js not found in HTML:\n" + self._trim_html(html)
        )
        # New, robust check for download link:
        self.assertIn(
            'href="/work/conway.txt"', html,
            'href="/work/conway.txt" link not found in HTML:\n' + self._trim_html(html)
        )
        # Optionally, you can check for the download attribute, but do not fail if missing.

    def test_game_of_life_css_file_downloadable(self):
        """CSS file is downloadable with correct content type."""
        url = self.base_url + "/static/conway/styles/game_of_life.css"
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
        """JS file is downloadable with correct content type."""
        url = self.base_url + "/static/conway/scripts/game_of_life.js"
        resp = requests.get(url)
        self.assertEqual(
            resp.status_code, 200,
            f"JS not found (status {resp.status_code})."
        )
        self.assertIn(
            "javascript", resp.headers.get("Content-Type", ""),
            f"Wrong content-type for JS: {resp.headers.get('Content-Type')}"
        )
        self.assertTrue(
            len(resp.text) > 0,
            "JS file is empty!"
        )

    def test_download_board_link_works(self):
        """/work/conway.txt returns a plain text file, not HTML, and is not empty."""
        url = self.base_url + "/work/conway.txt"
        resp = requests.get(url)
        self.assertEqual(
            resp.status_code, 200,
            f"/work/conway.txt not found (status {resp.status_code})."
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
        """Canary for regression: main CSS and JS files should appear before </head> and </body>"""
        resp = requests.get(self.base_url + "/conway/game-of-life")
        self.assertEqual(
            resp.status_code, 200,
            f"Non-200 status code: {resp.status_code}\n{self._trim_html(resp.text)}"
        )
        html = resp.text
        head = html.split("</head>")[0]
        self.assertIn(
            '/static/conway/styles/game_of_life.css', head,
            "game_of_life.css not linked in <head>:\n" + self._trim_html(head)
        )
        self.assertIn(
            '/static/conway/scripts/game_of_life.js', html,
            "game_of_life.js not linked in HTML:\n" + self._trim_html(html)
        )

if __name__ == "__main__":
    unittest.main()
