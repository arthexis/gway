import os
import unittest

from gway.sigils import Sigil  


class SigilTests(unittest.TestCase):

    def test_basic_resolution_with_dict(self):
        data = {"name": "Alice"}
        s = Sigil("Hello [name|Guest]")
        self.assertEqual(s % data, "Hello Alice")

    def test_fallback_used_when_key_missing(self):
        data = {}
        s = Sigil("Hello [user|Guest]")
        self.assertEqual(s % data, "Hello Guest")

    def test_case_insensitive_lookup(self):
        data = {"USER": "admin"}
        s = Sigil("Logged in as [user|none]")
        self.assertEqual(s % data, "Logged in as admin")

    def test_multiple_sigils_in_text(self):
        data = {"x": 10, "y": 20}
        s = Sigil("Coordinates: [x|0], [y|0]")
        self.assertEqual(s % data, "Coordinates: 10, 20")

    def test_nested_sigil_raises_error(self):
        with self.assertRaises(ValueError):
            Sigil("Invalid [[nested]] sigil")

    def test_empty_key_raises_error(self):
        with self.assertRaises(ValueError):
            Sigil("Oops [|fallback]") % {}

    def test_empty_fallback_raises_error(self):
        with self.assertRaises(ValueError):
            Sigil("Oops [key|]") % {}

    def test_dict_finder_fallback(self):
        s = Sigil("Hello [who|there]")
        self.assertEqual(s % {}, "Hello there")

    def test_callable_finder(self):
        def finder(key, fallback=None):
            return {"k1": "v1", "k2": "v2"}.get(key, fallback)

        s = Sigil("Vals: [k1|a], [k2|b], [k3|c]")
        self.assertEqual(s % finder, "Vals: v1, v2, c")

    def test_environment_variable(self):
        os.environ["MY_VAR"] = "from_env"
        def finder(key, fallback=None):
            return os.getenv(key, fallback)

        s = Sigil("Value: [MY_VAR|default]")
        self.assertEqual(s % finder, "Value: from_env")

    def test_resolves_to_empty_string(self):
        s = Sigil("Value: [missing|]")
        with self.assertRaises(ValueError):
            _ = s % {}

    def test_non_string_init_raises(self):
        with self.assertRaises(TypeError):
            Sigil(123)

    def test_non_callable_or_dict_finder_raises(self):
        s = Sigil("[key|val]")
        with self.assertRaises(TypeError):
            s % 42


if __name__ == "__main__":
    unittest.main()
