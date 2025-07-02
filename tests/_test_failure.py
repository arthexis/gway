# file: test_failure.py

import unittest

class SimpleFailTest(unittest.TestCase):
    def test_always_fails(self):
        self.assertEqual(1, 0, "This test always fails (hopefully)")

if __name__ == '__main__':
    unittest.main()
