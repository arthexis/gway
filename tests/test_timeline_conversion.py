import unittest
from gway import gw


class TimelineConversionTests(unittest.TestCase):
    def test_convert_date(self):
        result = gw.clock.convert_date("2025-08-01", "O", "P")
        self.assertEqual(result, "0206-02-19")

    def test_identity(self):
        self.assertEqual(
            gw.clock.convert_date("2025-08-01", "P", "P"), "2025-08-01"
        )

