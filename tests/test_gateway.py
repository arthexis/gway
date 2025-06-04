import os
import unittest

from gway import gw


class GatewayTests(unittest.TestCase):

    def test_awg_find_cable_callable(self):
        func = gw.awg.find_cable
        self.assertTrue(callable(func))
        results = func(meters=40)
        gw.debug(f"AWG Find cable {results=}")
        self.assertTrue(results)

    def test_builtin_loading(self):
        self.assertTrue(hasattr(gw, 'hello_world'))
        self.assertTrue(callable(gw.hello_world))

    def test_function_wrapping_and_call(self):
        result = gw.hello_world(name="test1", greeting="test2")
        self.assertIsInstance(result, dict)
        self.assertEqual(result['message'], "Test2, Test1!")
        self.assertTrue(hasattr(gw, 'hello_world'))

    def test_context_injection_and_resolve(self):
        gw.context['username'] = 'testuser'
        resolved = gw.resolve("Hello [username|guest]")
        self.assertEqual(resolved, "Hello testuser")

        resolved_fallback = gw.resolve("Welcome [missing|default_user]")
        self.assertEqual(resolved_fallback, "Welcome default_user")

    def test_multiple_sigils(self):
        gw.context['nickname'] = 'Alice'
        gw.context['age'] = 30
        resolved = gw.resolve("User: [nickname|unknown], Age: [age|0]")
        self.assertEqual(resolved, "User: Alice, Age: 30")

    def test_env_variable_resolution(self):
        os.environ['TEST_ENV'] = 'env_value'
        resolved = gw.resolve("Env: [TEST_ENV|fallback]")
        self.assertEqual(resolved, "Env: env_value")

    def test_env_variable_resolution_lower(self):
        os.environ['TEST_ENV'] = 'env_value'
        resolved = gw.resolve("Env: [test_env|fallback]")
        self.assertEqual(resolved, "Env: env_value")

    def test_missing_env_variable(self):
        resolved = gw.resolve("Env: [MISSING_ENV|fallback]")
        self.assertEqual(resolved, "Env: fallback")

    def test_missing_project_raises_attribute_error(self):
        with self.assertRaises(AttributeError):
            _ = gw.non_existent_project

    def test_variadic_positional_args(self):
        result = gw.tests.variadic_positional("a", "b", "c")
        self.assertEqual(result["args"], ("a", "b", "c"))

    def test_variadic_keyword_args(self):
        result = gw.tests.variadic_keyword(key1="val1", key2="val2")
        self.assertEqual(result["kwargs"], {"key1": "val1", "key2": "val2"})

    def test_variadic_args_and_kwargs(self):
        result = gw.tests.variadic_both("x", "y", keyA="A", keyB="B")
        self.assertEqual(result["args"], ("x", "y"))
        self.assertEqual(result["kwargs"], {"keyA": "A", "keyB": "B"})


if __name__ == "__main__":
    unittest.main()
