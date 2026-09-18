"""Smoke tests for quick upgrade validation."""

import unittest
from datetime import datetime

from gway import gw


class SmokeTests(unittest.TestCase):
    """Minimal checks executed during upgrade smoke runs."""

    def test_gateway_clock_now_returns_string(self) -> None:
        """Ensure the clock helper is available and returns a timestamp string."""

        timestamp = gw.clock.now()
        self.assertIsInstance(timestamp, datetime)
        self.assertTrue(timestamp.isoformat())


if __name__ == "__main__":
    unittest.main()
