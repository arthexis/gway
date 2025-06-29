# file: tests/test_auth_charger.py

import unittest
import subprocess
import time
import socket
import os
import base64
import requests
from gway import gw

CDV_PATH = "work/basic_auth.cdv"
TEST_USER = "admin"
TEST_PASS = "admin"

def _remove_test_user(user=TEST_USER):
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
        cls.proc = subprocess.Popen(
            ["gway", "-r", "website"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        cls._wait_for_port(8888, timeout=18)
        time.sleep(2)
        cls.base_url = "http://127.0.0.1:8888"

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
                with socket.create_connection(("localhost", port), timeout=1):
                    return
            except OSError:
                time.sleep(0.2)
        raise TimeoutError(f"Port {port} not responding after {timeout} seconds")

    def setUp(self):
        _remove_test_user()
        gw.web.auth.create_user(TEST_USER, TEST_PASS, allow=CDV_PATH, force=True)

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
        url = self.base_url + "/cookies/cookie-jar"
        resp = requests.get(url)
        self.assertEqual(
            resp.status_code, 200,
            f"Expected 200 for unauthenticated /cookies/cookie-jar, got {resp.status_code}"
        )
        headers = self._auth_header(TEST_USER, TEST_PASS)
        resp2 = requests.get(url, headers=headers)
        self.assertEqual(
            resp2.status_code, 200,
            f"Expected 200 for authenticated /cookies/cookie-jar, got {resp2.status_code}"
        )
        self.assertIn("cookie", resp2.text.lower())

if __name__ == "__main__":
    unittest.main()
