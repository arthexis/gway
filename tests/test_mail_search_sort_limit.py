import unittest
import os
from datetime import datetime, timedelta
from unittest.mock import patch
from email.mime.text import MIMEText
from gway import gw

class FakeIMAP:
    instances = []
    count = 3
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
        self.last_search = (charset, list(criteria))
        ids = ' '.join(str(i+1) for i in range(self.count))
        return 'OK', [ids.encode()]
    def fetch(self, mail_id, mode):
        idx = int(mail_id.decode() if isinstance(mail_id, bytes) else mail_id)
        msg = MIMEText('body')
        msg['Subject'] = f'subject {idx}'
        msg['From'] = 'sender@example.com'
        dt = datetime(2024, 1, 1) + timedelta(days=idx)
        msg['Date'] = dt.strftime('%a, %d %b %Y %H:%M:%S +0000')
        return 'OK', [(None, msg.as_bytes())]
    def close(self):
        pass
    def logout(self):
        pass

class MailSearchSortLimitTests(unittest.TestCase):
    def setUp(self):
        os.environ['MAIL_SENDER'] = 'test@example.com'
        os.environ['MAIL_PASSWORD'] = 'secret'
        os.environ['IMAP_SERVER'] = 'imap.example.com'
        os.environ['IMAP_PORT'] = '993'
        FakeIMAP.instances.clear()

    def tearDown(self):
        for var in ['MAIL_SENDER','MAIL_PASSWORD','IMAP_SERVER','IMAP_PORT']:
            os.environ.pop(var, None)

    def test_default_sort_descending_limit_10(self):
        FakeIMAP.count = 12
        with patch('imaplib.IMAP4_SSL', FakeIMAP):
            results = gw.mail.search('hello')
            self.assertEqual(len(results), 10)
            self.assertEqual(results[0]['subject'], 'subject 12')
            self.assertEqual(results[-1]['subject'], 'subject 3')

    def test_reverse_sort_and_custom_limit(self):
        FakeIMAP.count = 5
        with patch('imaplib.IMAP4_SSL', FakeIMAP):
            results = gw.mail.search('hello', limit=2, reverse=True)
            self.assertEqual(len(results), 2)
            self.assertEqual(results[0]['subject'], 'subject 1')
            self.assertEqual(results[1]['subject'], 'subject 2')

if __name__ == '__main__':
    unittest.main()
