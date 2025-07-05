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
        self.selected_mailbox = None
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
        self.selected_mailbox = mailbox
    def search(self, charset, criteria):
        if isinstance(criteria, str):
            criteria.encode(self._encoding)
        else:
            criteria.decode(self._encoding)
        self.last_search = (charset, criteria)
        return 'OK', [b'1']
    def fetch(self, mail_id, mode):
        msg = MIMEText('respuesta')
        return 'OK', [(None, msg.as_bytes())]
    def close(self):
        pass
    def logout(self):
        pass

class MailUTF8Tests(unittest.TestCase):
    def setUp(self):
        os.environ['MAIL_SENDER'] = 'test@example.com'
        os.environ['MAIL_PASSWORD'] = 'secret'
        os.environ['IMAP_SERVER'] = 'imap.example.com'
        os.environ['IMAP_PORT'] = '993'
        FakeIMAP.instances.clear()

    def tearDown(self):
        for var in ['MAIL_SENDER','MAIL_PASSWORD','IMAP_SERVER','IMAP_PORT']:
            os.environ.pop(var, None)

    def test_unicode_subject_search(self):
        with patch('imaplib.IMAP4_SSL', FakeIMAP):
            content, attachments = gw.mail.search('instalación')
            self.assertEqual(content, 'respuesta')
            fake = FakeIMAP.instances[0]
            self.assertTrue(fake.utf8_enabled)
            self.assertEqual(fake.last_search[0], None)

    def test_search_uses_inbox_uppercase(self):
        """Ensure search operates with FakeIMAP when selecting 'INBOX'."""
        with patch('imaplib.IMAP4_SSL', FakeIMAP):
            content, attachments = gw.mail.search('hello')
            self.assertEqual(content, 'respuesta')
            fake = FakeIMAP.instances[0]
            self.assertEqual(fake.selected_mailbox, 'INBOX')

if __name__ == '__main__':
    unittest.main()
