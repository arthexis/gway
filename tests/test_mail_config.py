import unittest
import os
from gway import gw

class MailConfigTests(unittest.TestCase):
    def tearDown(self):
        for var in ['MAIL_SENDER','MAIL_PASSWORD','IMAP_SERVER','IMAP_PORT']:
            os.environ.pop(var, None)

    def test_missing_config_raises(self):
        os.environ.pop('MAIL_SENDER', None)
        with self.assertRaises(RuntimeError):
            gw.mail.search('hello')

if __name__ == '__main__':
    unittest.main()
