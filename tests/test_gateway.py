import os
import unittest
from unittest import mock

from gway.gateway import Gateway, load_project, load_builtins


# A dummy function for testing dynamic loading
def dummy_function(param1: str, param2: str = "default"):
    """Dummy function for testing."""
    return {"result": f"{param1}-{param2}"}


class GatewayTests(unittest.TestCase):

    def setUp(self):
        # Patch load_builtins to return a fake builtin function
        self.patcher_builtins = mock.patch('gway.gateway.load_builtins', return_value={'hello_world': dummy_function})
        self.mock_builtins = self.patcher_builtins.start()

        # Create Gateway instance
        self.gw = Gateway(root=os.getcwd())

    def tearDown(self):
        self.patcher_builtins.stop()

    def test_builtin_loading(self):
        # Builtin function should be available
        self.assertTrue(hasattr(self.gw.builtin, 'hello_world'))
        self.assertTrue(callable(getattr(self.gw.builtin, 'hello_world')))

    def test_function_wrapping_and_call(self):
        # Call the hello_world function (used as the "dummy_builtin" in the tests)
        result = self.gw.hello_world(param1="test1", param2="test2")
        self.assertIsInstance(result, dict)
        self.assertEqual(result['result'], "test1-test2")
        # Ensure that hello_world is an attribute of the Gateway instance (not in results)
        self.assertTrue(hasattr(self.gw, 'hello_world'))

    def test_context_injection_and_resolve(self):
        # Prepare a value with sigil syntax [key|fallback]
        self.gw.context['username'] = 'testuser'
        resolved = self.gw.resolve("Hello [username|guest]")
        self.assertEqual(resolved, "Hello testuser")

        # If key missing, fallback should be used
        resolved_fallback = self.gw.resolve("Welcome [missing|default_user]")
        self.assertEqual(resolved_fallback, "Welcome default_user")

    def test_multiple_sigils(self):
        # Prepare a string with multiple sigils
        self.gw.context['name'] = 'Alice'
        self.gw.context['age'] = 30
        resolved = self.gw.resolve("User: [name|unknown], Age: [age|0]")
        self.assertEqual(resolved, "User: Alice, Age: 30")

    def test_environment_variable_resolution(self):
        # Simulate an environment variable
        os.environ['TEST_ENV'] = 'env_value'
        resolved = self.gw.resolve("Env: [TEST_ENV|fallback]")
        self.assertEqual(resolved, "Env: env_value")

    def test_missing_environment_variable(self):
        # Ensure the fallback is used when the environment variable is missing
        resolved = self.gw.resolve("Env: [MISSING_ENV|fallback]")
        self.assertEqual(resolved, "Env: fallback")

    def test_missing_project_raises_attribute_error(self):
        with self.assertRaises(AttributeError):
            _ = self.gw.non_existent_project

    def test_wrap_callable_argument_injection(self):
        # Simulate missing optional argument; it should auto-fill
        result = self.gw.hello_world(param1="only_param1")
        self.assertEqual(result['result'], "only_param1-default")

    def test_used_context_tracking(self):
        # Call function with sigils
        self.gw.context = {'key1': 'val1'}
        _ = self.gw.resolve("[key1|fallback]")
        # Ensure that the key was tracked
        self.assertIn('key1', self.gw.used_context)  # Should now track used context


if __name__ == "__main__":
    unittest.main()
