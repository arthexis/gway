import unittest
import sys
import io
from gway.gateway import Gateway
from gway.builtins import *

# Currently, verbose and abort cannot be tested in the same way as the other functions

class GatewayBuiltinsTests(unittest.TestCase):

    def setUp(self):
        # Redirect stdout to capture printed messages
        self.sio = io.StringIO()
        sys.stdout = self.sio

        # Ensure the Gateway instance is initialized with an empty root path
        self.gw = Gateway()

    def tearDown(self):
        # Restore stdout
        sys.stdout = sys.__stdout__

    def test_builtins_functions(self):
        # Test if the builtins can be accessed directly and are callable
        try:
            self.gw.print("test")
            self.gw.abort("Abort test")
            self.gw.hello_world()

        except AttributeError as e:
            self.fail(f"AttributeError occurred: {e}")

    def test_hello_world(self):
        # Call the hello_world function
        self.gw.hello_world()

        # Check if "Hello, World!" was printed
        self.assertIn("Hello, World!", self.sio.getvalue().strip())


if __name__ == "__main__":
    unittest.main()
