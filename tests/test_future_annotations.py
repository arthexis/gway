from __future__ import annotations


import argparse
import unittest

import gway.console as console


def _future_func(*, value: float = 1.0):
    return value


class FutureAnnotationsTests(unittest.TestCase):
    def test_add_func_args_parses_future_annotations(self):
        parser = argparse.ArgumentParser()
        console.add_func_args(parser, _future_func)
        parsed = parser.parse_args(["--value", "2.5"])
        self.assertEqual(parsed.value, 2.5)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

