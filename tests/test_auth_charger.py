# file: tests/test_auth_charger.py

import unittest
import subprocess
import time
import socket
import os
import base64
import requests
import random
import string
from gway import gw
from gway.builtins import is_test_flag

CDV_PATH = os.path.abspath("work/basic_auth.cdv")  # Use production path
# Generate a random user/pass for each test run
def _rand_str(n=10):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=n))
TEST_USER = f"testuser_{_rand_str(8)}"
TEST_PASS = _rand_str(16)

def _remove_test_user(user=TEST_USER):
    """Remove the test user from the allowlist file, if present."""
    if not os.path.exists(CDV_PATH):
        return
    lines = []
    with open(CDV_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip().startswith(f"{user}:"):
                lines.append(line)
    with open(CDV_PATH, "w", encoding="utf-8") as f:
        f.writelines(lines)

class AuthChargerStatusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _remove_test_user()
        # Start the server
        cls.proc = subprocess.Popen(
            ["gway", "-r", "test/website"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        cls._wait_for_port(18888, timeout=18)
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
        _remove_test_user()

    @staticmethod
    def _wait_for_port(port, timeout=15):
        start = time.time()
        while time.time() - start < timeout:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=1):
                    return
            except OSError:
                time.sleep(0.2)
        raise TimeoutError(f"Port {port} not responding after {timeout} seconds")

    def setUp(self):
        _remove_test_user()
        gw.web.auth.create_user(TEST_USER, TEST_PASS, allow=CDV_PATH, force=True)
        # Optionally, log to help debug
        # print(f"Created test user {TEST_USER} in {CDV_PATH}")

    def tearDown(self):
        _remove_test_user()

    def _auth_header(self, username, password):
        up = f"{username}:{password}"
        b64 = base64.b64encode(up.encode()).decode()
        return {"Authorization": f"Basic {b64}"}

    def test_unauthenticated_blocked_on_charger_status(self):
        url = self.base_url + "/ocpp/csms/charger-status"
        resp = requests.get(url)
        self.assertEqual(
            resp.status_code, 401,
            f"Expected 401 for unauthenticated /ocpp/csms/charger-status, got {resp.status_code}"
        )

    def test_authenticated_allows_on_charger_status(self):
        url = self.base_url + "/ocpp/csms/charger-status"
        headers = self._auth_header(TEST_USER, TEST_PASS)
        resp = requests.get(url, headers=headers)
        self.assertEqual(
            resp.status_code, 200,
            f"Expected 200 for authenticated /ocpp/csms/charger-status, got {resp.status_code}"
        )
        self.assertIn("OCPP", resp.text)

    def test_cookie_jar_no_auth_required(self):
        url = self.base_url + "/web/cookies/cookie-jar"
        resp = requests.get(url)
        self.assertEqual(
            resp.status_code, 200,
            f"Expected 200 for unauthenticated /web/cookies/cookie-jar, got {resp.status_code}"
        )
        headers = self._auth_header(TEST_USER, TEST_PASS)
        resp2 = requests.get(url, headers=headers)
        self.assertEqual(
            resp2.status_code, 200,
            f"Expected 200 for authenticated /web/cookies/cookie-jar, got {resp2.status_code}"
        )
        self.assertIn("cookie", resp2.text.lower())

    @unittest.skipUnless(is_test_flag("screen"), "Screen tests disabled")
    def test_charger_status_screenshot(self):
        """Capture charger status page screenshot using basic auth."""
        screenshot_dir = Path("work/screenshots")
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        screenshot_file = screenshot_dir / "charger_status.png"
        url = f"http://{TEST_USER}:{TEST_PASS}@127.0.0.1:18888/ocpp/csms/charger-status"
        try:
            gw.web.auto.capture_page_source(url, screenshot=str(screenshot_file))
        except Exception as e:
            self.skipTest(f"Webdriver unavailable: {e}")
        self.assertTrue(screenshot_file.exists())

if __name__ == "__main__":
    unittest.main()
