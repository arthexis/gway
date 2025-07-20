import unittest
import os
import sys
from io import StringIO
from unittest.mock import patch
from gway import gw

class NotifyBuiltinTests(unittest.TestCase):
    def setUp(self):
        self.out = StringIO()
        self.orig = sys.stdout
        sys.stdout = self.out

    def tearDown(self):
        sys.stdout = self.orig
        os.environ.pop('ADMIN_EMAIL', None)

    def test_console_fallback(self):
        with patch.object(gw.studio.screen, 'notify', side_effect=Exception('fail')):
            with patch.object(gw.mail, 'send') as mock_send:
                gw.notify('hello world', title='T')
                mock_send.assert_not_called()
        self.assertIn('hello world', self.out.getvalue())

    def test_email_fallback(self):
        os.environ['ADMIN_EMAIL'] = 'test@example.com'
        with patch.object(gw.studio.screen, 'notify', side_effect=Exception('fail')):
            with patch.object(gw.mail, 'send') as mock_send:
                gw.notify('msg', title='Notice')
                mock_send.assert_called_once()

if __name__ == '__main__':
    unittest.main()
