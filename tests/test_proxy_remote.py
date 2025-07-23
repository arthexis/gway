import unittest
from gway.builtins import is_test_flag
import subprocess
import time
import socket
import sys
import tempfile
import shutil
import requests

@unittest.skipUnless(is_test_flag("proxy"), "Proxy tests disabled")
class ProxyRemoteTests(unittest.TestCase):
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

    def setUp(self):
        self.procs = []
        self.temp_dirs = []

    def tearDown(self):
        for p in self.procs:
            p.terminate()
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
        for d in self.temp_dirs:
            shutil.rmtree(d, ignore_errors=True)

    def _start_remote(self):
        remote_dir = tempfile.mkdtemp(prefix="remote_gw_")
        self.temp_dirs.append(remote_dir)
        proc = subprocess.Popen([
            sys.executable, "-m", "gway", "-r", "test/etron/cloud"
        ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        self.procs.append(proc)
        self._wait_for_port(19000, timeout=15)
        time.sleep(1)
        return proc

    def _start_local(self):
        local_dir = tempfile.mkdtemp(prefix="local_gw_")
        self.temp_dirs.append(local_dir)
        proc = subprocess.Popen([
            sys.executable, "-m", "gway", "-r", "test/etron/local_proxy"
        ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        self.procs.append(proc)
        self._wait_for_port(19900, timeout=15)
        time.sleep(1)
        return proc

    def test_remote_first_then_local(self):
        self._start_remote()
        self._start_local()
        resp = requests.get("http://127.0.0.1:18888/web/cookies/cookie-jar")
        self.assertEqual(resp.status_code, 200)

    def test_local_fallback_then_remote(self):
        self._start_local()
        resp = requests.get("http://127.0.0.1:18888/web/cookies/cookie-jar")
        self.assertNotEqual(resp.status_code, 200)
        self._start_remote()
        time.sleep(2)
        resp2 = requests.get("http://127.0.0.1:18888/web/cookies/cookie-jar")
        self.assertEqual(resp2.status_code, 200)
