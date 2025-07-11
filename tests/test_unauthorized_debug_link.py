import unittest
from gway import gw
from paste.fixture import TestApp

class UnauthorizedDebugLinkTests(unittest.TestCase):
    def setUp(self):
        gw.update_modes(debug=True)
        self.app = gw.web.app.setup_app("dummy")
        # simple route that always triggers unauthorized
        self.app.route('/unauth', callback=lambda: gw.web.error.unauthorized("Access denied"))
        self.client = TestApp(self.app)

    def tearDown(self):
        gw.update_modes(debug=False)

    def test_link_to_original_page_shown(self):
        resp = self.client.get('/unauth', expect_errors=True)
        self.assertEqual(resp.status, 401)
        body = resp.body.decode()
        self.assertIn('Go to original page', body)
        self.assertIn('/unauth', body)

if __name__ == '__main__':
    unittest.main()
