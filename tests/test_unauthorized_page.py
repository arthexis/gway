import unittest
from gway import gw
from paste.fixture import TestApp

class UnauthorizedPageTests(unittest.TestCase):
    def setUp(self):
        gw.update_modes(debug=False)
        self.app = gw.web.app.setup_app("dummy")
        self.app.route('/unauth', callback=lambda: gw.web.error.unauthorized("Access denied"))
        self.client = TestApp(self.app)

    def test_redirect_page(self):
        resp = self.client.get('/unauth', headers={'Referer': '/orig'}, expect_errors=True)
        self.assertEqual(resp.status, 401)
        self.assertIn('text/html', resp.header('Content-Type'))
        body = resp.body.decode()
        self.assertIn('Username and password are required', body)
        self.assertIn('meta http-equiv', body)
        self.assertIn('/orig', body)

if __name__ == '__main__':
    unittest.main()
