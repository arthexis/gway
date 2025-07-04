import unittest
from gway.sigils import Resolver

class ResolverDefaultTests(unittest.TestCase):
    def test_resolve_returns_default(self):
        resolver = Resolver([])
        self.assertEqual(resolver.resolve('[missing]', default='fallback'), 'fallback')

    def test_resolve_raises_with_sentinel(self):
        resolver = Resolver([])
        with self.assertRaises(KeyError):
            resolver.resolve('[missing]')

if __name__ == '__main__':
    unittest.main()
