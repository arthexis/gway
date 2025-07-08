import unittest
import importlib.util
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("site", Path(__file__).resolve().parents[1] / "projects" / "web" / "site.py")
site = importlib.util.module_from_spec(spec)
spec.loader.exec_module(site)

class FeedbackViewTests(unittest.TestCase):
    def test_feedback_form_display(self):
        html = site.view_feedback()
        self.assertIn("<form", html)
        self.assertIn("name=\"name\"", html)
        self.assertIn("name=\"email\"", html)
        self.assertIn("name=\"topic\"", html)
        self.assertIn("name=\"message\"", html)

    def test_feedback_post_calls_issue(self):
        class FakeRequest:
            def __init__(self):
                self.method = "POST"
        with patch('bottle.request', FakeRequest()):
            with patch.object(site, '_create_github_issue', return_value='http://example.com') as ci:
                html = site.view_feedback(name='A', email='a@example.com', topic='Test', message='Hello')
                self.assertIn('Thank you', html)
                ci.assert_called_once()

if __name__ == '__main__':
    unittest.main()
