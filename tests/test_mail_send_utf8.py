import unittest
import os
from unittest.mock import patch
from email.header import decode_header, make_header
from gway import gw

class FakeSMTP:
    instances = []
    def __init__(self, server, port):
        self.server = server
        self.port = port
        FakeSMTP.instances.append(self)
    def starttls(self):
        pass
    def login(self, user, password):
        pass
    def send_message(self, msg):
        self.message = msg
    def quit(self):
        pass

class MailSendUTF8Tests(unittest.TestCase):
    def setUp(self):
        os.environ['MAIL_SENDER'] = 'test@example.com'
        os.environ['MAIL_PASSWORD'] = 'secret'
        os.environ['SMTP_SERVER'] = 'smtp.example.com'
        os.environ['SMTP_PORT'] = '587'
        FakeSMTP.instances.clear()

    def tearDown(self):
        for var in ['MAIL_SENDER','MAIL_PASSWORD','SMTP_SERVER','SMTP_PORT']:
            os.environ.pop(var, None)

    def test_send_utf8_subject_and_body(self):
        with patch('smtplib.SMTP', FakeSMTP):
            result = gw.mail.send('Suj\u00e9', 'Cuerpo con acci\u00f3n', to='a@example.com', threaded=False)
            self.assertEqual(result, 'Email sent successfully to a@example.com')
            fake = FakeSMTP.instances[0]
            subject = str(make_header(decode_header(fake.message['Subject'])))
            self.assertEqual(subject, 'Suj\u00e9')
            body = fake.message.get_payload(decode=True).decode('utf-8')
            self.assertEqual(body, 'Cuerpo con acci\u00f3n')

if __name__ == '__main__':
    unittest.main()
