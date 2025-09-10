import builtins
from unittest.mock import patch

import gway.console as console


def test_wizard_prompts_for_missing():
    def dummy(a: int, b: int = 2):
        return a + b

    setattr(console.gw, "dummy", dummy)
    console.gw.wizard_enabled = True

    inputs = iter(["3", ""])  # a, b (accept default)
    with patch.object(builtins, "input", side_effect=lambda _: next(inputs)):
        results, last = console.process([["dummy"]])

    assert results == [5]
    assert last == 5

    delattr(console.gw, "dummy")
    console.gw.wizard_enabled = False


def test_wizard_collects_before_run():
    executed = []

    def first(a: int):
        executed.append("first")
        return a

    def second(b: int):
        executed.append("second")
        return b

    setattr(console.gw, "first", first)
    setattr(console.gw, "second", second)
    console.gw.wizard_enabled = True

    inputs = iter(["1", "2"])

    def fake_input(prompt):
        assert executed == []
        return next(inputs)

    with patch.object(builtins, "input", side_effect=fake_input):
        results, last = console.process([["first"], ["second"]])

    assert results == [1, 2]
    assert executed == ["first", "second"]
    assert last == 2

    delattr(console.gw, "first")
    delattr(console.gw, "second")
    console.gw.wizard_enabled = False


def test_wizard_guesses_names():
    def dummy(a: int):
        return a

    setattr(console.gw, "dummy", dummy)
    console.gw.wizard_enabled = True

    inputs = iter(["", "5"])  # accept guess, provide param

    with patch.object(builtins, "input", side_effect=lambda _: next(inputs)):
        results, last = console.process([["dum"]])

    assert results == [5]
    assert last == 5

    delattr(console.gw, "dummy")
    console.gw.wizard_enabled = False
