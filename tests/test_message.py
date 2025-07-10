import unittest
import importlib.util
from pathlib import Path
from unittest import mock


class FakeRequest:
    def __init__(self):
        self.cookies = {}
    def get_cookie(self, name, default=None):
        return self.cookies.get(name, default)


class FakeResponse:
    def __init__(self):
        self.set_calls = []
    def set_cookie(self, name, value, **kwargs):
        self.set_calls.append((name, value, kwargs))


class FakeApp:
    def __init__(self, message=True, cookies=True):
        self._message = message
        self._cookies = cookies
    def is_setup(self, name):
        if name == 'web.message':
            return self._message
        if name == 'web.cookies':
            return self._cookies
        return False


class MessageTests(unittest.TestCase):
    @staticmethod
    def _load_module(rel):
        path = Path(__file__).resolve().parents[1] / 'projects' / 'web' / rel
        spec = importlib.util.spec_from_file_location(rel.replace('.py',''), path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    @classmethod
    def setUpClass(cls):
        cls.message = cls._load_module('message.py')
        cls.cookies = cls._load_module('cookies.py')

    def setUp(self):
        self.request = FakeRequest()
        self.response = FakeResponse()
        # patch cookies request/response
        self.preq = mock.patch.object(self.cookies, 'request', self.request)
        self.pres = mock.patch.object(self.cookies, 'response', self.response)
        self.preq.start()
        self.pres.start()
        # patch gw.web modules
        self.orig_app = self.message.gw.web.app
        self.orig_cookies = self.message.gw.web.cookies
        self.message.gw.web.app = FakeApp(message=True, cookies=True)
        self.message.gw.web.cookies = self.cookies

    def tearDown(self):
        self.preq.stop()
        self.pres.stop()
        self.message.gw.web.app = self.orig_app
        self.message.gw.web.cookies = self.orig_cookies

    def test_write_appends_and_limits(self):
        self.request.cookies['cookies_accepted'] = 'yes'
        for i in range(5):
            self.message.write(f'm{i}')
            self.request.cookies['message'] = self.response.set_calls[-1][1]
        value = self.cookies.get('message')
        self.assertEqual(value.split('\n'), ['m1', 'm2', 'm3', 'm4'])

    def test_write_noop_without_consent(self):
        self.message.write('hi')
        self.assertIsNone(self.cookies.get('message'))
        self.assertEqual(self.response.set_calls, [])

    def test_write_noop_when_disabled(self):
        self.request.cookies['cookies_accepted'] = 'yes'
        self.message.gw.web.app = FakeApp(message=False, cookies=True)
        self.message.write('hello')
        self.assertIsNone(self.cookies.get('message'))
        self.assertEqual(self.response.set_calls, [])


if __name__ == '__main__':
    unittest.main()
