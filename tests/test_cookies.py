import unittest
import importlib.util
from pathlib import Path
from unittest import mock

# Dynamically load the cookies module from projects/web/cookies.py
cookies_path = Path(__file__).resolve().parents[1] / "projects" / "web" / "cookies.py"
spec = importlib.util.spec_from_file_location("webcookies", cookies_path)
cookies = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cookies)

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

class CookiesUtilTests(unittest.TestCase):
    def setUp(self):
        self.request = FakeRequest()
        self.response = FakeResponse()
        self.preq = mock.patch.object(cookies, 'request', self.request)
        self.pres = mock.patch.object(cookies, 'response', self.response)
        self.preq.start()
        self.pres.start()

    def tearDown(self):
        self.preq.stop()
        self.pres.stop()

    def test_set_and_get_when_accepted(self):
        self.request.cookies['cookies_accepted'] = 'yes'
        cookies.set('foo', 'bar')
        self.assertEqual(len(self.response.set_calls), 1)
        name, value, _ = self.response.set_calls[0]
        self.assertEqual((name, value), ('foo', 'bar'))
        # get should read from request
        self.request.cookies['foo'] = 'bar'
        self.assertEqual(cookies.get('foo'), 'bar')
        self.assertIsNone(cookies.get('missing'))
        self.assertTrue(cookies.accepted())

    def test_set_ignored_when_not_accepted(self):
        cookies.set('foo', 'bar')
        self.assertEqual(self.response.set_calls, [])
        # cookies_accepted cookie can always be set
        cookies.set('cookies_accepted', 'yes')
        self.assertEqual(len(self.response.set_calls), 1)
        self.assertEqual(self.response.set_calls[0][0], 'cookies_accepted')

    def test_remove_when_accepted(self):
        self.request.cookies['cookies_accepted'] = 'yes'
        cookies.remove('foo')
        self.assertEqual(len(self.response.set_calls), 2)
        for call in self.response.set_calls:
            name, value, params = call
            self.assertEqual(name, 'foo')
            self.assertEqual(value, '')
            self.assertEqual(params['expires'], 'Thu, 01 Jan 1970 00:00:00 GMT')
        self.assertFalse(self.response.set_calls[0][2]['secure'])
        self.assertTrue(self.response.set_calls[1][2]['secure'])

    def test_remove_noop_when_not_accepted(self):
        cookies.remove('foo')
        self.assertEqual(self.response.set_calls, [])

    def test_append_when_accepted(self):
        self.request.cookies['cookies_accepted'] = 'yes'
        self.request.cookies['bag'] = 'a=1|b=2'
        result = cookies.append('bag', 'c', '3')
        self.assertEqual(result, ['a=1', 'b=2', 'c=3'])
        self.assertEqual(self.response.set_calls[-1][0], 'bag')
        self.assertEqual(self.response.set_calls[-1][1], 'a=1|b=2|c=3')

    def test_append_noop_when_not_accepted(self):
        self.request.cookies['bag'] = 'a=1|b=2'
        result = cookies.append('bag', 'c', '3')
        self.assertEqual(result, [])
        self.assertEqual(self.response.set_calls, [])

    def test_accepted_checks_cookie_value(self):
        self.request.cookies['cookies_accepted'] = 'yes'
        self.assertTrue(cookies.accepted())
        self.request.cookies['cookies_accepted'] = 'no'
        self.assertFalse(cookies.accepted())
        del self.request.cookies['cookies_accepted']
        self.assertFalse(cookies.accepted())

if __name__ == '__main__':
    unittest.main()
