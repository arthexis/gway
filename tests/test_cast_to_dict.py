import unittest
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "cast_mod", Path(__file__).resolve().parents[1] / "projects" / "cast.py"
)
cast_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cast_mod)


class ToDictSanitizeTests(unittest.TestCase):
    def test_default_max_depth(self):
        data = {"a": {"b": {"c": {"d": {"e": 1}}}}}
        result = cast_mod.to_dict(data)
        self.assertEqual(result, {"a": {"b": {"c": {"d": "..."}}}})

    def test_override_max_depth(self):
        data = {"a": {"b": {"c": {"d": {"e": 1}}}}}
        result = cast_mod.to_dict(data, max_depth=2)
        self.assertEqual(result, {"a": {"b": "..."}})

    def test_json_string_input(self):
        text = '{"x": {"y": {"z": 2}}}'
        result = cast_mod.to_dict(text, max_depth=2)
        self.assertEqual(result, {"x": {"y": "..."}})


if __name__ == "__main__":
    unittest.main()
