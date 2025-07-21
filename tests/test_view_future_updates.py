import unittest
from gway import gw
from paste.fixture import TestApp
from unittest.mock import patch

class ViewFutureUpdatesTests(unittest.TestCase):
    def setUp(self):
        self.app = gw.web.app.setup_app("web.site")
        self.client = TestApp(self.app)

    def test_newer_version_notice(self):
        with patch("requests.get") as mock_get:
            mock_get.return_value.json.return_value = {"info": {"version": "9.9.9"}}
            mock_get.return_value.raise_for_status = lambda: None
            changelog = "Changelog\n=========\n\nUnreleased\n----------\n- pending\n\n0.1\n"
            with patch("pathlib.Path.read_text", return_value=changelog):
                resp = self.client.get("/web/site/future-updates")
        self.assertEqual(resp.status, 200)
        body = resp.body.decode()
        self.assertIn("newer version of GWAY pending", body)
        self.assertIn("9.9.9", body)
        self.assertIn("pending", body)

if __name__ == "__main__":
    unittest.main()
