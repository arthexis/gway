import unittest
from gway import gw
from paste.fixture import TestApp

class ProjectIndexViewTests(unittest.TestCase):
    def setUp(self):
        self.app = gw.web.app.setup_app("dummy")
        self.client = TestApp(self.app)

    def test_index_route(self):
        resp = self.client.get("/dummy")
        self.assertEqual(resp.status, 200)
        self.assertIn("Dummy Index", resp.body.decode())
        resp2 = self.client.get("/dummy/")
        self.assertEqual(resp2.status, 200)
        self.assertIn("Dummy Index", resp2.body.decode())

if __name__ == "__main__":
    unittest.main()
