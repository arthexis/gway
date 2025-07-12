# file: tests/test_proxy_fallback.py

import unittest
from gway.builtins import is_test_flag
import subprocess
import time
import socket
import os
import tempfile
import shutil
import asyncio
import requests

from gway import gw

KNOWN_TAG = "FFFFFFFF"

@unittest.skipUnless(is_test_flag("integration"), "Integration tests disabled")
class ProxyFallbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.local_dir = tempfile.mkdtemp(prefix="local_gw_")
        cls.local_proc = subprocess.Popen(
            ["gway", "-r", "test/etron/local_proxy"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        cls._wait_for_port(19900, timeout=15)
        time.sleep(1)

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "local_proc", None):
            cls.local_proc.terminate()
            try:
                cls.local_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.local_proc.kill()
        if getattr(cls, "remote_proc", None):
            cls.remote_proc.terminate()
            try:
                cls.remote_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.remote_proc.kill()
        shutil.rmtree(getattr(cls, "local_dir", ""), ignore_errors=True)
        shutil.rmtree(getattr(cls, "remote_dir", ""), ignore_errors=True)

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

    def test_offline_then_proxy(self):
        async def run_session():
            await gw.ocpp.evcs.simulate_cp.__wrapped__(
                0,
                "127.0.0.1",
                19900,
                KNOWN_TAG,
                "SIM1",
                1,
                1,
                1,
                1,
            )
        asyncio.run(run_session())

        records = os.path.join("work", "ocpp", "records", "SIM1")
        self.assertTrue(os.path.isdir(records))
        self.assertTrue(os.listdir(records))

        resp = requests.get("http://127.0.0.1:18888/web/cookies/cookie-jar")
        self.assertNotEqual(resp.status_code, 200)

        self.__class__.remote_dir = tempfile.mkdtemp(prefix="remote_gw_")
        self.__class__.remote_proc = subprocess.Popen(
            ["gway", "-r", "test/etron/cloud"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        self._wait_for_port(19000, timeout=15)
        time.sleep(2)

        resp2 = requests.get("http://127.0.0.1:18888/web/cookies/cookie-jar")
        self.assertEqual(resp2.status_code, 200)


