import unittest
from pathlib import Path
from gway import gw


class ToDictSanitizeTests(unittest.TestCase):
    def test_default_max_depth(self):
        data = {"a": {"b": {"c": {"d": {"e": 1}}}}}
        result = gw.cast.to_dict(data)
        self.assertEqual(result, {"a": {"b": {"c": {"d": "..."}}}})

    def test_override_max_depth(self):
        data = {"a": {"b": {"c": {"d": {"e": 1}}}}}
        result = gw.cast.to_dict(data, max_depth=2)
        self.assertEqual(result, {"a": {"b": "..."}})

    def test_json_string_input(self):
        text = '{"x": {"y": {"z": 2}}}'
        result = gw.cast.to_dict(text, max_depth=2)
        self.assertEqual(result, {"x": {"y": "..."}})


if __name__ == "__main__":
    unittest.main()
