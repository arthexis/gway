import unittest
from gway.builtins import is_test_flag
import os
import base64
import random
import string
import subprocess
import time
import socket
import asyncio
import requests

from gway import gw

CDV_PATH = os.path.abspath("work/basic_auth.cdv")

def _rand_str(n=10):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=n))

TEST_USER = f"testuser_{_rand_str(8)}"
TEST_PASS = _rand_str(16)

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

def _auth_header(username, password):
    up = f"{username}:{password}"
    b64 = base64.b64encode(up.encode()).decode()
    return {"Authorization": f"Basic {b64}"}

@unittest.skipUnless(is_test_flag("ocpp"), "OCPP tests disabled")
class ChargerDashboardRefreshTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _remove_test_user()
        cls.proc = subprocess.Popen(
            ["gway", "-r", "test/website"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        cls._wait_for_port(18888, timeout=18)
        cls._wait_for_port(19999, timeout=18)
        time.sleep(2)

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "proc", None):
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.proc.kill()
        _remove_test_user()
        time.sleep(1)

    def setUp(self):
        _remove_test_user()
        gw.web.auth.create_user(TEST_USER, TEST_PASS, allow=CDV_PATH, force=True)

    def tearDown(self):
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
    @unittest.skipUnless(is_test_flag("ocpp"), "OCPP tests disabled")

    def test_dashboard_updates_with_simulator(self):
        async def run_sim_and_check():
            sim_task = asyncio.create_task(
                gw.ocpp.evcs.simulate_cp.__wrapped__(
                    0,
                    "localhost",
                    19999,
                    "FFFFFFFF",
                    "ocpp/csms/SIMDASH",
                    2,
                    1,
                    1,
                    1,
                    username=TEST_USER,
                    password=TEST_PASS,
                )
            )
            await asyncio.sleep(3)
            resp = await asyncio.to_thread(
                requests.post,
                "http://127.0.0.1:18888/render/ocpp/csms/charger-status/charger_list",
                headers=_auth_header(TEST_USER, TEST_PASS),
                timeout=5,
            )
            self.assertIn("SIMDASH", resp.text)
            self.assertRegex(resp.text, r"kWh\.</td>\s*<td class=\"value\">[0-9.]+")
            await sim_task
        asyncio.run(run_sim_and_check())

if __name__ == "__main__":
    unittest.main()
