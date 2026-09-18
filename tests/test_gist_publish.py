import unittest
from unittest.mock import patch, MagicMock
from gway import gw


class GistPublishTests(unittest.TestCase):
    def test_publish_returns_url(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"html_url": "http://gist.example/1"}
        with patch("requests.post", return_value=mock_resp) as post:
            with patch.object(gw.hub, "get_token", return_value="TOKEN"):
                with patch.object(gw.results, "get_results", return_value={"a": 1}):
                    url = gw.gist.publish()
        self.assertEqual(url, "http://gist.example/1")
        post.assert_called_once()


if __name__ == "__main__":
    unittest.main()
