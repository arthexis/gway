import unittest
import json
from gway import gw
import unittest.mock as mock
import importlib.util


class FakeCookies:
    def __init__(self):
        self.store = {}
    def set(self, name, value, **kwargs):
        self.store[name] = value
    def get(self, name, default=None):
        return self.store.get(name, default)
    def delete(self, name, **kwargs):
        self.store.pop(name, None)
    # Some parts of the code use remove()
    remove = delete
    def accepted(self):
        return True

class FakeApp:
    def is_setup(self, name):
        return True

class QPigFarmButtonTests(unittest.TestCase):
    def setUp(self):
        # Preserve existing app/cookie objects
        self._orig_app = getattr(gw.web, 'app', None)
        self._orig_cookies = getattr(gw.web, 'cookies', None)
        gw.web.app = FakeApp()
        gw.web.cookies = FakeCookies()
        gw.web.cookies.set('cookies_accepted', 'yes')
        self.time_patch = mock.patch('time.time', lambda: 0)
        self.time_patch.start()
        # Load the underlying module for constants
        path = gw.resource('projects', 'games', 'qpig.py')
        spec = importlib.util.spec_from_file_location('qpig_mod', str(path))
        self.qpig_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.qpig_mod)

    def tearDown(self):
        self.time_patch.stop()
        gw.web.app = self._orig_app
        gw.web.cookies = self._orig_cookies

    def test_buy_small_and_adopt(self):
        gw.web.cookies.set('qpig_mc', '1000')
        gw.games.qpig.view_qpig_farm(action='buy_small')
        self.assertEqual(int(gw.web.cookies.get('qpig_enc_small')), 2)
        self.assertEqual(float(gw.web.cookies.get('qpig_mc')), 1000 - self.qpig_mod.SMALL_COST)

        gw.games.qpig.view_qpig_farm(action='adopt')
        self.assertEqual(int(gw.web.cookies.get('qpig_pigs')), 2)
        self.assertEqual(int(gw.web.cookies.get('qpig_avail')), self.qpig_mod.DEFAULT_AVAILABLE - 1)

    def test_buy_and_place_veggie(self):
        gw.web.cookies.set('qpig_mc', '1000')
        gw.web.cookies.set('qpig_offer_kind', 'carrot')
        gw.web.cookies.set('qpig_offer_qty', '2')
        gw.web.cookies.set('qpig_offer_price', '10')
        gw.games.qpig.view_qpig_farm(action='buy_veggie')
        veggies = json.loads(gw.web.cookies.get('qpig_veggies'))
        self.assertEqual(veggies.get('carrot'), 2)
        self.assertEqual(float(gw.web.cookies.get('qpig_mc')), 1000 - 20)

        gw.games.qpig.view_qpig_farm(action='place_carrot')
        veggies_after = json.loads(gw.web.cookies.get('qpig_veggies'))
        food = json.loads(gw.web.cookies.get('qpig_food'))
        self.assertEqual(veggies_after.get('carrot'), 1)
        self.assertEqual(len(food), 1)
        self.assertEqual(food[0][0], 'carrot')

if __name__ == '__main__':
    unittest.main()
