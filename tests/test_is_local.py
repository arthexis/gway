import unittest
from pathlib import Path
from gway import gw


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
        self.assertTrue(gw.web.server.is_local(request=req, host="127.0.0.1"))

    def test_non_local_address_returns_false(self):
        req = FakeRequest("8.8.8.8")
        self.assertFalse(gw.web.server.is_local(request=req, host="127.0.0.1"))


if __name__ == "__main__":
    unittest.main()
