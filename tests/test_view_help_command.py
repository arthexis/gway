import unittest
from gway import gw
from paste.fixture import TestApp
from unittest.mock import patch

class ViewHelpCommandTests(unittest.TestCase):
    def setUp(self):
        self.app = gw.web.app.setup_app("web.site")
        self.client = TestApp(self.app)

    def test_invalid_command_returns_error(self):
        with patch.object(gw.web.server, "is_local", return_value=True):
            resp = self.client.get("/web/site/help", {"topic": ">unknown"})
            self.assertEqual(resp.status, 200)
            body = resp.body.decode()
            self.assertIn("<pre>", body)

if __name__ == "__main__":
    unittest.main()
