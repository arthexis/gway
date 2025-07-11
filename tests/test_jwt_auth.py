import unittest
import jwt
from gway import gw

web = gw.load_project('web')

class JwtAuthChallengeTests(unittest.TestCase):
    class FakeRequest:
        def __init__(self, token):
            self.headers = {'authorization': f'Bearer {token}'}

    class FakeResponse:
        def __init__(self):
            self.status_code = None
            self.headers = {}

    def test_valid_token(self):
        secret = 'test-secret'
        token = jwt.encode({'sub': 'alice'}, secret, algorithm='HS256')
        web.auth.clear()
        web.auth.config_jwt(secret=secret, algorithms=['HS256'], engine='fastapi')
        ok = web.auth.is_authorized(strict=True, context={'request': self.FakeRequest(token), 'response': self.FakeResponse()})
        self.assertTrue(ok)
        web.auth.clear()

    def test_invalid_token(self):
        secret = 'test-secret'
        token = jwt.encode({'sub': 'alice'}, 'wrong', algorithm='HS256')
        web.auth.clear()
        web.auth.config_jwt(secret=secret, algorithms=['HS256'], engine='fastapi')
        ok = web.auth.is_authorized(strict=True, context={'request': self.FakeRequest(token), 'response': self.FakeResponse()})
        self.assertFalse(ok)
        web.auth.clear()

if __name__ == '__main__':
    unittest.main()
