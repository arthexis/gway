from gway.dispatcher import _strict_fallback_missing
from gway.expression import parse_managed_branches


def test_double_pipe_operator_is_preserved() -> None:
    branches = parse_managed_branches("primary.check||secondary.check|:offline")
    assert [branch.operator for branch in branches] == [None, "||", "|"]
    assert branches[-1].literal == "offline"


def test_double_pipe_literal_is_terminal() -> None:
    branches = parse_managed_branches("primary.check||:offline|ignored.check")
    assert len(branches) == 2
    assert branches[-1].operator == "||"
    assert branches[-1].literal == "offline"


def test_strict_fallback_advances_on_none_and_empty_sets() -> None:
    assert _strict_fallback_missing(None)
    assert _strict_fallback_missing(set())
    assert _strict_fallback_missing(frozenset())


def test_strict_fallback_keeps_other_falsey_values() -> None:
    assert not _strict_fallback_missing(False)
    assert not _strict_fallback_missing(0)
    assert not _strict_fallback_missing("")
    assert not _strict_fallback_missing([])
    assert not _strict_fallback_missing({})
    assert not _strict_fallback_missing(())
