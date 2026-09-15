from gway.dispatcher import _strict_fallback_missing
from gway.expression import parse_managed_branches


def test_double_pipe_operator_is_preserved() -> None:
    branches = parse_managed_branches("primary.check||secondary.check|offline.status")
    assert [branch.operator for branch in branches] == [None, "||", "|"]
    assert branches[-1].project == "offline"
    assert branches[-1].args == ("status",)


def test_double_pipe_keeps_all_fallback_branches() -> None:
    branches = parse_managed_branches("primary.check||offline.status|ignored.check")
    assert len(branches) == 3
    assert branches[1].operator == "||"
    assert branches[1].project == "offline"
    assert branches[2].operator == "|"
    assert branches[2].project == "ignored"


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
