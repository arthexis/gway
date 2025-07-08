# file: tests/test_sigils.py

import unittest
from gway import Sigil, Spool, gw, __


class SigilTests(unittest.TestCase):

    def test_basic_resolution_with_dict(self):
        data = {"name": "Alice"}
        s = Sigil("Hello [name]")
        self.assertEqual(s % data, "Hello Alice")

    def test_unresolved_key_raises(self):
        data = {}
        s = Sigil("Hello [user]")
        with self.assertRaises(KeyError):
            _ = s % data

    def test_case_insensitive_lookup(self):
        data = {"USER": "admin"}
        s = Sigil("Logged in as [user]")
        # Your code tries lower/upper/case variants
        self.assertEqual(s % data, "Logged in as admin")

    def test_multiple_sigils_in_text(self):
        data = {"x": 10, "y": 20}
        s = Sigil("Coordinates: [x], [y]")
        self.assertEqual(s % data, "Coordinates: 10, 20")

    def test_quoted_literal_returns_literal(self):
        s = Sigil('Key is ["LITERAL"]')
        self.assertEqual(s % {}, 'Key is LITERAL')

    def test_unresolved_unquoted_raises(self):
        s = Sigil("Oops [nope]")
        with self.assertRaises(KeyError):
            _ = s % {}

    def test_list_sigils(self):
        s = Sigil("A [foo] and [bar]")
        self.assertEqual(s.list_sigils(), ["[foo]", "[bar]"])

    def test_repr_and_str(self):
        s = Sigil("[val]")
        self.assertIn("[val]", str(s))
        self.assertIn("[val]", repr(s))

    def test_make_lookup_with_callable_variants(self):
        def finder(key, _):
            if key == "FOO_BAR":
                return "bar"
        s = Sigil("Value [FOO-BAR]")
        self.assertEqual(s.resolve(finder), "Value bar")

    def test_dotted_and_spaced_paths(self):
        class Obj:
            pass
        obj = Obj()
        obj.name = "Widget"
        data = {"app": {"name": "dict"}, "obj": obj}
        self.assertEqual(Sigil("[app.name]") % data, "dict")
        self.assertEqual(Sigil("[app name]") % data, "dict")
        self.assertEqual(Sigil("[obj.name]") % data, "Widget")

    def test_standalone_and_embedded_non_string(self):
        data = {"num": 7, "info": {"a": 1}}
        # Standalone should return raw value
        self.assertEqual(Sigil("[num]") % data, 7)
        self.assertEqual(Sigil("[info]") % data, {"a": 1})
        # Embedded should stringify/serialize
        from json import dumps
        self.assertEqual(Sigil("Value [num]") % data, "Value 7")
        self.assertEqual(Sigil("Info=[info]") % data, "Info=" + dumps({"a": 1}))

    def test_underscore_path_denied(self):
        data = {"obj": {"_secret": 42}, "_root": {"val": 1}}
        with self.assertRaises(KeyError):
            Sigil("[obj._secret]") % data
        with self.assertRaises(KeyError):
            Sigil("[obj _secret]") % data
        # Accessing leading underscore as first segment is allowed
        self.assertEqual(Sigil("[_root.val]") % data, 1)

    def test_unquote_helper(self):
        from gway.sigils import _unquote
        self.assertEqual(_unquote('"hello"'), "hello")
        self.assertEqual(_unquote("'world'"), "world")
        self.assertEqual(_unquote("plain"), "plain")

class SpoolTests(unittest.TestCase):
    def setUp(self):
        self.mapping = {"A": "apple", "B": "banana", "C": "cucumber"}

    def test_spool_basic_resolve(self):
        spool = Spool("[B]", "[A]", "[C]")
        # Should resolve the *first* that is found (so B="banana")
        self.assertEqual(spool.resolve(self.mapping), "banana")

    def test_spool_with_literal_and_missing(self):
        spool = Spool("foo", '[B]', '["literal"]')
        # "foo" becomes Sigil("foo"), so will raise. Next, [B] will resolve.
        self.assertEqual(spool.resolve(self.mapping), "foo")

    def test_spool_resolve_raises_when_none_resolved(self):
        spool = Spool("[X]", "[Y]")
        with self.assertRaises(KeyError):
            spool.resolve(self.mapping)

    def test_spool_append_and_extend(self):
        spool = Spool("[A]")
        spool.append("[B]")
        spool.extend(["[C]"])
        self.assertEqual([str(x) for x in spool], ["[A]", "[B]", "[C]"])

    def test_spool_sequence_protocol(self):
        spool = Spool("[A]", "[B]")
        self.assertEqual(len(spool), 2)
        self.assertEqual(str(spool[0]), "[A]")
        self.assertEqual([str(s) for s in spool], ["[A]", "[B]"])

    def test_spool_resolve_with_resolver_object(self):
        spool = Spool("[X]", "[A]")
        # Provide a gw-style object with .resolve()
        self.assertEqual(spool.resolve(self.mapping), "apple")

    def test_spool_flatten_and_str(self):
        spool = Spool(["[A]", ["[B]", "[C]"]])
        self.assertEqual(len(spool), 3)
        self.assertEqual(str(spool), "[A] | [B] | [C]")

if __name__ == "__main__":
    unittest.main()
