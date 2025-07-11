import unittest
from gway import gw
from paste.fixture import TestApp

class ViewMashupTests(unittest.TestCase):
    def setUp(self):
        self.app = gw.web.app.setup_app("games")
        self.client = TestApp(self.app)

    def test_mashup_returns_combined_content(self):
        resp = self.client.get("/games/massive-snake+game-of-life")
        self.assertEqual(resp.status, 200)
        text = resp.body.decode()
        self.assertIn("Massive Snake", text)
        self.assertIn("Game of Life", text)

if __name__ == "__main__":
    unittest.main()
