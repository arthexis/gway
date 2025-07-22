import unittest
from gway import gw
from paste.fixture import TestApp
from unittest.mock import patch


class ViewStudioBenchTests(unittest.TestCase):
    def setUp(self):
        self.app = gw.web.app.setup_app("studio.studio")
        self.client = TestApp(self.app)

    def test_bench_lists_subviews(self):
        with patch.object(gw.web.app, "render_template", lambda **kw: kw["content"]):
            resp = self.client.get("/studio/studio/studio-bench")
        self.assertEqual(resp.status, 200)
        text = resp.body.decode()
        self.assertIn("/studio/screen/animate-gif", text)


if __name__ == "__main__":
    unittest.main()
