import os
import unittest
from unittest import mock

from gway import gw


class GatewayTests(unittest.TestCase):

    def test_builtin_loading(self):
        # Builtin function should be available
        self.assertTrue(hasattr(gw, 'hello_world'))
        self.assertTrue(callable(getattr(gw, 'hello_world')))

    def test_function_wrapping_and_call(self):
        # Call the hello_world function (used as the "dummy_builtin" in the tests)
        result = gw.hello_world(name="test1", greeting="test2")
        self.assertIsInstance(result, dict)
        self.assertEqual(result['message'], "Test2, Test1!")
        # Ensure that hello_world is an attribute of the Gateway instance (not in results)
        self.assertTrue(hasattr(gw, 'hello_world'))

    def test_context_injection_and_resolve(self):
        # Prepare a value with sigil syntax [key|fallback]
        gw.context['username'] = 'testuser'
        resolved = gw.resolve("Hello [username|guest]")
        self.assertEqual(resolved, "Hello testuser")

        # If key missing, fallback should be used
        resolved_fallback = gw.resolve("Welcome [missing|default_user]")
        self.assertEqual(resolved_fallback, "Welcome default_user")

    def test_multiple_sigils(self):
        # Prepare a string with multiple sigils
        gw.context['nickname'] = 'Alice'
        gw.context['age'] = 30
        resolved = gw.resolve("User: [nickname|unknown], Age: [age|0]")
        self.assertEqual(resolved, "User: Alice, Age: 30")

    def test_environment_variable_resolution(self):
        # Simulate an environment variable
        os.environ['TEST_ENV'] = 'env_value'
        resolved = gw.resolve("Env: [TEST_ENV|fallback]")
        self.assertEqual(resolved, "Env: env_value")

    def test_missing_environment_variable(self):
        # Ensure the fallback is used when the environment variable is missing
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