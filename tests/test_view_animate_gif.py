import unittest
from gway import gw
from paste.fixture import TestApp
from unittest.mock import patch

class ViewAnimateGifTests(unittest.TestCase):
    def setUp(self):
        self.app = gw.web.app.setup_app("studio.screen")
        self.client = TestApp(self.app)

    def test_post_triggers_animation(self):
        import importlib
        screen_mod = importlib.import_module(
            gw.studio.screen.animate_gif.__module__
        )
        with patch.object(screen_mod, "animate_gif", return_value="/tmp/out.gif") as ag, \
             patch.object(gw.web.app, "render_template", lambda **kw: kw["content"]):
            resp = self.client.post(
                "/studio/screen/animate-gif",
                {"pattern": "frames", "output_gif": "result.gif"},
            )
        self.assertEqual(resp.status, 200)
        text = resp.body.decode()
        self.assertIn("result.gif", text)
        ag.assert_called_once_with("frames", output_gif="result.gif")

if __name__ == "__main__":
    unittest.main()
