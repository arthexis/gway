import unittest
import os
from unittest.mock import patch, MagicMock
from gway import gw

class WhatsAppSendTests(unittest.TestCase):
    def setUp(self):
        os.environ['WHATS_TOKEN'] = 'tkn'
        os.environ['WHATS_PHONE_ID'] = '123'

    def tearDown(self):
        os.environ.pop('WHATS_TOKEN', None)
        os.environ.pop('WHATS_PHONE_ID', None)

    def test_send_message_calls_api(self):
        fake_resp = MagicMock()
        fake_resp.json.return_value = {'ok': True}
        with patch('requests.post', return_value=fake_resp) as mock_post:
            res = gw.web.chat.whats.send_message('+1', 'hi', preview_url=True)
            self.assertEqual(res, {'ok': True})
            mock_post.assert_called_once()

    def test_missing_credentials_returns_error(self):
        os.environ.pop('WHATS_TOKEN')
        os.environ.pop('WHATS_PHONE_ID')
        res = gw.web.chat.whats.send_message('+1', 'hi')
        self.assertIn('error', res)

if __name__ == '__main__':
    unittest.main()
