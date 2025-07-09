import unittest
from unittest.mock import patch
from gway import gw
import sys
import os

site = gw.web.site

class FeedbackViewTests(unittest.TestCase):
    def test_feedback_form_display(self):
        html = site.view_feedback()
        self.assertIn("<form", html)
        self.assertIn("name=\"name\"", html)
        self.assertIn("name=\"email\"", html)
        self.assertIn("name=\"topic\"", html)
        self.assertIn("name=\"message\"", html)
        self.assertIn("publicly displayed", html)

    def test_feedback_post_calls_issue(self):
        class FakeRequest:
            def __init__(self):
                self.method = "POST"
        with patch('bottle.request', FakeRequest()):
            with patch.dict(os.environ, {'GH_TOKEN': 'x'}):
                with patch('requests.post') as p:
                    p.return_value.status_code = 201
                    p.return_value.json.return_value = {'html_url': 'http://example.com'}
                    html = site.view_feedback(name='A', email='a@example.com', topic='Test', message='Hello')
                    self.assertIn('Thank you', html)
                    p.assert_called_once()
                    body = p.call_args.kwargs['json']['body']
                    self.assertNotIn('a@example.com', body)

if __name__ == '__main__':
    unittest.main()
