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
            with patch.object(gw.lcd, 'show', side_effect=Exception('lcd fail')):
                with patch.object(gw.mail, 'send') as mock_send:
                    result = gw.notify('hello world', title='T')
                    mock_send.assert_not_called()
        self.assertEqual(result, 'console')
        self.assertIn('hello world', self.out.getvalue())

    def test_email_fallback(self):
        os.environ['ADMIN_EMAIL'] = 'test@example.com'
        with patch.object(gw.studio.screen, 'notify', side_effect=Exception('fail')):
            with patch.object(gw.lcd, 'show', side_effect=Exception('lcd fail')):
                with patch.object(gw.mail, 'send') as mock_send:
                    result = gw.notify('msg', title='Notice')
                    mock_send.assert_called_once()
        self.assertEqual(result, 'email')

    def test_lcd_fallback(self):
        with patch.object(gw.studio.screen, 'notify', side_effect=Exception('fail')):
            with patch.object(gw.lcd, 'show') as mock_lcd:
                with patch.object(gw.mail, 'send') as mock_send:
                    result = gw.notify('lcd msg', title='LCD Title', timeout=5)
                    mock_lcd.assert_called_once()
                    args, kwargs = mock_lcd.call_args
                    self.assertIn('LCD Title', args[0])
                    self.assertIn('lcd msg', args[0])
                    self.assertEqual(kwargs.get('hold'), 5)
                    self.assertTrue(kwargs.get('wrap'))
                    mock_send.assert_not_called()
        self.assertEqual(result, 'lcd')

if __name__ == '__main__':
    unittest.main()
