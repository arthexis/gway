import unittest
import os
from unittest.mock import patch
from email.mime.text import MIMEText
from gway import gw


class FakeIMAP:
    instances = []
    def __init__(self, server, port):
        self.server = server
        self.port = port
        self._encoding = 'ascii'
        self.utf8_enabled = False
        FakeIMAP.instances.append(self)
    def login(self, user, password):
        pass
    def enable(self, capability):
        if capability.upper() == 'UTF8=ACCEPT':
            self._encoding = 'utf-8'
            self.utf8_enabled = True
            return 'OK', [b'enabled']
        raise Exception('unsupported')
    def select(self, mailbox):
        pass
    def search(self, charset, *criteria):
        for item in criteria:
            if isinstance(item, str):
                item.encode(self._encoding)
            else:
                item.decode(self._encoding)
        self.last_search = (charset, list(criteria))
        return 'OK', [b'1']
    def fetch(self, mail_id, mode):
        msg = MIMEText('respuesta')
        return 'OK', [(None, msg.as_bytes())]
    def close(self):
        pass
    def logout(self):
        pass

class MailQuoteEscapeTests(unittest.TestCase):
    def setUp(self):
        os.environ['MAIL_SENDER'] = 'test@example.com'
        os.environ['MAIL_PASSWORD'] = 'secret'
        os.environ['IMAP_SERVER'] = 'imap.example.com'
        os.environ['IMAP_PORT'] = '993'
        FakeIMAP.instances.clear()

    def tearDown(self):
        for var in ['MAIL_SENDER','MAIL_PASSWORD','IMAP_SERVER','IMAP_PORT']:
            os.environ.pop(var, None)

    def test_subject_with_quotes(self):
        with patch('imaplib.IMAP4_SSL', FakeIMAP):
            content, attachments = gw.mail.read('He said "Hi"')
            self.assertEqual(content, 'respuesta')
            fake = FakeIMAP.instances[0]
            expected = ['SUBJECT', '"He said \\"Hi\\""']
            self.assertEqual(fake.last_search[1], expected)
            self.assertTrue(fake.utf8_enabled)

if __name__ == '__main__':
    unittest.main()
