import os
import unittest
from gway import gw
from paste.fixture import TestApp

class SnakeGameTests(unittest.TestCase):
    BOARD = "work/shared/games/massive_snake.json"
    ASC = "work/games/ascensions.cdv"

    def setUp(self):
        for path in (self.BOARD, self.ASC):
            p = gw.resource(path)
            if os.path.exists(p):
                os.remove(p)
        self.app = gw.web.app.setup_app("games")
        self.client = TestApp(self.app)

    def tearDown(self):
        for path in (self.BOARD, self.ASC):
            p = gw.resource(path)
            if os.path.exists(p):
                os.remove(p)

    def test_hegemony_player_present(self):
        resp = self.client.get("/games/massive-snake")
        self.assertEqual(resp.status, 200)
        text = resp.body.decode()
        self.assertIn("Hegemony", text)

    def test_leaderboard_view(self):
        gw.cdv.update(self.ASC, "Tester", count="2")
        resp = self.client.get("/games/snake-leaderboard")
        self.assertEqual(resp.status, 200)
        text = resp.body.decode()
        self.assertIn("Ascension Leaderboard", text)
        self.assertIn("Tester", text)
