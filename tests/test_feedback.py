import unittest
from unittest.mock import patch
from gway import gw
import sys
import os

site = gw.web.site

class FeedbackViewTests(unittest.TestCase):
    def test_feedback_form_display(self):
        with patch.dict(os.environ, {"GITHUB_TOKEN": "x"}):
            html = site.view_feedback()
            self.assertIn("<form", html)
            self.assertIn("name=\"name\"", html)
            self.assertIn("name=\"email\"", html)
            self.assertIn("name=\"topic\"", html)
            self.assertIn("name=\"message\"", html)
            self.assertIn("publicly displayed", html)
            self.assertIn("Create an Issue Report", html)

    def test_feedback_form_missing_token_with_mail(self):
        env = {
            "MAIL_SENDER": "a",
            "MAIL_PASSWORD": "b",
            "SMTP_SERVER": "smtp",
            "SMTP_PORT": "25",
        }
        with patch.dict(os.environ, env, clear=True):
            html = site.view_feedback()
            self.assertIn("<form", html)
            self.assertIn("GitHub issue creation unavailable", html)

    def test_feedback_form_missing_token_no_mail(self):
        with patch.dict(os.environ, {}, clear=True):
            html = site.view_feedback()
            self.assertIn("Feedback unavailable", html)

    def test_feedback_post_calls_issue(self):
        class FakeRequest:
            def __init__(self):
                self.method = "POST"
        with patch('bottle.request', FakeRequest()):
            with patch.dict(os.environ, {'GITHUB_TOKEN': 'x'}):
                with patch('requests.post') as p:
                    p.return_value.status_code = 201
                    p.return_value.json.return_value = {'html_url': 'http://example.com'}
                    html = site.view_feedback(name='A', email='a@example.com', topic='Test', message='Hello', create_issue=True)
                    self.assertIn('Thank you', html)
                    p.assert_called_once()
                    body = p.call_args.kwargs['json']['body']
                    self.assertNotIn('a@example.com', body)

    def test_feedback_post_without_checkbox(self):
        class FakeRequest:
            def __init__(self):
                self.method = "POST"
        with patch('bottle.request', FakeRequest()):
            with patch.dict(os.environ, {'GITHUB_TOKEN': 'x'}):
                with patch('requests.post') as p:
                    with patch.object(gw.mail, 'send') as mail_send:
                        html = site.view_feedback(name='A', email='a@example.com', topic='Test', message='Hello')
                        self.assertIn('Thank you', html)
                        p.assert_not_called()
                        mail_send.assert_called_once()

    def test_feedback_issue_failure_falls_back_to_mail(self):
        class FakeRequest:
            def __init__(self):
                self.method = "POST"
        with patch('bottle.request', FakeRequest()):
            with patch.dict(os.environ, {'GITHUB_TOKEN': 'x'}):
                with patch.object(gw.hub, 'create_issue', side_effect=RuntimeError('fail')):
                    with patch.object(gw.mail, 'send') as mail_send:
                        html = site.view_feedback(name='A', email='a@example.com', topic='Test', message='Hello', create_issue=True)
                        self.assertIn('feedback sent via email', html)
                        mail_send.assert_called_once()

    def test_feedback_issue_missing_token_falls_back_to_mail(self):
        class FakeRequest:
            def __init__(self):
                self.method = "POST"
        with patch('bottle.request', FakeRequest()):
            env = {
                "MAIL_SENDER": "a",
                "MAIL_PASSWORD": "b",
                "SMTP_SERVER": "smtp",
                "SMTP_PORT": "25",
            }
            with patch.dict(os.environ, env, clear=True):
                with patch.object(gw.hub, 'create_issue', side_effect=RuntimeError('fail')):
                    with patch.object(gw.mail, 'send') as mail_send:
                        html = site.view_feedback(name='A', email='a@example.com', topic='Test', message='Hello', create_issue=True)
                        self.assertIn('feedback sent via email', html)
                        mail_send.assert_called_once()

if __name__ == '__main__':
    unittest.main()
