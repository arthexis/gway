# tests/test_gateway.py

import os
import unittest
from gway import gw

class GatewayTests(unittest.TestCase):
    def setUp(self):
        gw.context.clear()
        gw.results.clear()
        # Remove env variables
        if "TEST_SIGIL" in os.environ:
            del os.environ["TEST_SIGIL"]

    def tearDown(self):
        gw.context.clear()
        gw.results.clear()
        if "TEST_SIGIL" in os.environ:
            del os.environ["TEST_SIGIL"]

    def test_builtin_function_loads_and_works(self):
        self.assertTrue(hasattr(gw, 'hello_world'))
        func = gw.hello_world
        self.assertTrue(callable(func))
        result = func(name="Avon", greeting="Goodbye")
        self.assertIsInstance(result, dict)
        self.assertEqual(result["message"], "Goodbye, Avon!")

    def test_context_injection_and_resolve(self):
        gw.context["xuser"] = "bob"
        self.assertEqual(gw.resolve("Hello [xuser]"), "Hello bob")
        self.assertEqual(gw.resolve("Missing [nope]", "Fallback!"), "Fallback!")
        self.assertEqual(gw.resolve("Literal [\"foobar\"]"), "Literal foobar")

    def test_multiple_sigils_in_text(self):
        gw.context.update({"foo": "F", "bar": 7})
        text = "A=[foo] B=[bar]"
        self.assertEqual(gw.resolve(text), "A=F B=7")

    def test_env_variable_resolution_case_insensitive(self):
        os.environ["TEST_SIGIL"] = "abc"
        self.assertEqual(gw.resolve("Value: [TEST_SIGIL]"), "Value: abc")
        self.assertEqual(gw.resolve("Value: [test_sigil]"), "Value: abc")

    def test_explicit_arguments_are_not_resolved(self):
        from gway.sigils import Sigil, Spool
        gw.context.clear()
        gw.context["S"] = "sig"
        gw.context["P"] = "spl"
        def func(x=Spool("[P]"), y=Sigil("[S]")):
            return f"{x}-{y}"
        wrapped = gw.wrap_callable("bar_func", func)
        self.assertEqual(wrapped(x="override", y="stuff"), "override-stuff")

    def test_type_coercion_on_wrap(self):
        def func(x: int, y: float, z: bool, s: str):
            return (x, y, z, s)
        wrapped = gw.wrap_callable("typetest", func)
        result = wrapped(x="7", y="3.0", z="true", s=123)
        self.assertEqual(result, (7, 3.0, True, "123"))
        result2 = wrapped(x=4, y=1.5, z=False, s="hello")
        self.assertEqual(result2, (4, 1.5, False, "hello"))

    def test_subject_detection_and_result_storage(self):
        def foo(x=1): return x
        wrapped = gw.wrap_callable("run", foo)
        gw.results.clear()
        res = wrapped(x=42)
        self.assertEqual(res, 42)
        self.assertFalse("run" in gw.results)
        def foo2(bar=2): return {"bar": bar}
        wrapped2 = gw.wrap_callable("do_bar", foo2)
        gw.results.clear()
        res2 = wrapped2(bar=99)
        self.assertEqual(res2, {"bar": 99})
        self.assertTrue("bar" in gw.results)

    def test_wrap_callable_raises_on_unresolved_sigils(self):
        from gway.sigils import Sigil
        gw.context.clear()
        def func(x=Sigil("[NOT_PRESENT]")): return x
        wrapped = gw.wrap_callable("failtest", func)
        with self.assertRaises(KeyError):
            wrapped()

if __name__ == "__main__":
    unittest.main()
