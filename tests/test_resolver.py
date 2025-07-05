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

class ResolverLookupTests(unittest.TestCase):
    def setUp(self):
        self.resolver = Resolver([
            ('env', {}),
            ('ctx', {'foo_bar': 'spam'})
        ])

    def test_contains_and_get(self):
        self.assertTrue('[foo_bar]' in self.resolver)
        self.assertFalse('[missing]' in self.resolver)
        self.assertEqual(self.resolver['foo_bar'], 'spam')
        self.assertEqual(self.resolver.get('foo_bar'), 'spam')

    def test_keys_returns_union(self):
        self.assertIn('foo_bar', self.resolver.keys())

    def test_dash_underscore_item_access(self):
        self.resolver._search_order.append(('extra', {'hello-world': 'hi'}))
        self.assertEqual(self.resolver['hello-world'], 'hi')

    def test_env_variable_resolution(self):
        import os
        os.environ['SIGTEST'] = 'ok'
        env_resolver = Resolver([('env', {}), ('ctx', {})])
        try:
            self.assertEqual(env_resolver.resolve('[sigtest]'), 'ok')
        finally:
            del os.environ['SIGTEST']

if __name__ == '__main__':
    unittest.main()
