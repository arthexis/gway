import unittest
from unittest.mock import patch
from gway import gw
web = gw.load_project('web')


def make_resolver(mapping):
    def _resolve(*args, default="_raise"):
        for arg in args:
            if isinstance(arg, str) and arg.startswith("[") and arg.endswith("]"):
                if arg in mapping:
                    return mapping[arg]
                else:
                    continue
            else:
                return arg
        if default != "_raise":
            return default
        raise KeyError("unresolved")
    return _resolve


class BuildProtocolTests(unittest.TestCase):
    def test_bare_port(self):
        self.assertEqual(web.build_protocol("http", "8888"), "http://127.0.0.1:8888")

    def test_existing_protocol(self):
        result = web.build_protocol("https", "http://example.com:9000")
        self.assertEqual(result, "https://example.com:9000")

    def test_replace_zero_host(self):
        self.assertEqual(web.build_protocol("http", "0.0.0.0:123"), "http://127.0.0.1:123")


class BaseURLTests(unittest.TestCase):
    def test_base_url_ssl_vs_plain(self):
        mapping = {"[BASE_URL]": "example.com:8080", "[USE_HTTPS]": "1"}
        with patch.object(gw, "resolve", side_effect=make_resolver(mapping)):
            with patch.object(gw.cast, "to_bool", return_value=True):
                self.assertEqual(web.base_url(), "https://example.com:8080")

    def test_base_url_forces_plain_localhost(self):
        mapping = {"[BASE_URL]": "127.0.0.1:8080", "[USE_HTTPS]": "1"}
        with patch.object(gw, "resolve", side_effect=make_resolver(mapping)):
            with patch.object(gw.cast, "to_bool", return_value=True):
                self.assertEqual(web.base_url(), "http://127.0.0.1:8080")

    def test_base_ws_url_ssl_vs_plain(self):
        mapping = {
            "[BASE_URL]": "example.com:8000",
            "[WEBSOCKET_PORT]": "6789",
            "[USE_WSS]": "1",
        }
        with patch.object(gw, "resolve", side_effect=make_resolver(mapping)):
            with patch.object(gw.cast, "to_bool", return_value=True):
                self.assertEqual(web.base_ws_url(), "wss://example.com:6789")

    def test_base_ws_url_local_forced_ws(self):
        mapping = {
            "[BASE_URL]": "0.0.0.0:8000",
            "[WEBSOCKET_PORT]": "9000",
            "[USE_WSS]": "1",
        }
        with patch.object(gw, "resolve", side_effect=make_resolver(mapping)):
            with patch.object(gw.cast, "to_bool", return_value=True):
                self.assertEqual(web.base_ws_url(), "ws://127.0.0.1:9000")


if __name__ == "__main__":
    unittest.main()
