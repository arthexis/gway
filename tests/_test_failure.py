# file: test_failure.py

import unittest
import pytest
from gway.builtins import is_test_flag

@unittest.skipUnless(is_test_flag("failure"), "Failure tests disabled")
class SimpleFailTest(unittest.TestCase):
    @pytest.mark.xfail(reason="This test always fails", strict=False)
    def test_always_fails(self):
        self.assertEqual(1, 0, "This test always fails (hopefully)")

if __name__ == '__main__':
    unittest.main()
