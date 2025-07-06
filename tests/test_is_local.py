import unittest
import importlib.util
from pathlib import Path

# Dynamically load the server module to access is_local
server_path = Path(__file__).resolve().parents[1] / "projects" / "web" / "server.py"
spec = importlib.util.spec_from_file_location("webserver", server_path)
webserver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(webserver)


class FakeClient:
    def __init__(self, host):
        self.host = host


class FakeRequest:
    def __init__(self, addr):
        self.remote_addr = addr
        self.client = FakeClient(addr)


class IsLocalTests(unittest.TestCase):
    def test_local_address_returns_true(self):
        req = FakeRequest("127.0.0.1")
        self.assertTrue(webserver.is_local(request=req, host="127.0.0.1"))

    def test_non_local_address_returns_false(self):
        req = FakeRequest("8.8.8.8")
        self.assertFalse(webserver.is_local(request=req, host="127.0.0.1"))


if __name__ == "__main__":
    unittest.main()
