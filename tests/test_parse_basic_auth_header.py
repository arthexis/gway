import unittest
import base64
from gway import gw

web = gw.load_project('web')


class ParseBasicAuthHeaderTests(unittest.TestCase):
    def test_valid_header(self):
        username = 'foo'
        password = 'bar'
        creds = f"{username}:{password}".encode('utf-8')
        header = 'Basic ' + base64.b64encode(creds).decode()
        self.assertEqual(
            web.auth.parse_basic_auth_header(header),
            (username, password),
        )

    def test_invalid_headers(self):
        invalid_headers = [
            None,
            '',
            'Bearer abc',
            'Basic not-base64',
            'Basic ' + base64.b64encode(b'nocolon').decode(),
        ]
        for hdr in invalid_headers:
            with self.subTest(hdr=hdr):
                self.assertEqual(
                    web.auth.parse_basic_auth_header(hdr),
                    (None, None),
                )


if __name__ == '__main__':
    unittest.main()
