import unittest
from gway import gw

web = gw.load_project('web')

class ParseBearerTokenHeaderTests(unittest.TestCase):
    def test_valid_header(self):
        token = 'abc.def.ghi'
        header = 'Bearer ' + token
        self.assertEqual(web.auth.parse_bearer_token_header(header), token)

    def test_invalid_headers(self):
        invalid_headers = [None, '', 'Basic xyz', 'Bearer', 'Bearer ']
        for hdr in invalid_headers:
            with self.subTest(hdr=hdr):
                self.assertIsNone(web.auth.parse_bearer_token_header(hdr))

if __name__ == '__main__':
    unittest.main()
