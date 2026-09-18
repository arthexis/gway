import pytest

from gway.console import parse_recipe_context, process
from gway.tokens import chunk


def test_unknown_keyword_fails_cleanly(gateway):
    def echo(value: str):
        return value
    gateway.echo = gateway.wrap_callable("echo_value", echo)
    with pytest.raises(TypeError, match="Unknown argument"):
        process([["echo", "--missing", "x"]], gw_instance=gateway)


def test_parse_recipe_context():
    assert parse_recipe_context(["--site", "MTY", "--dry-run"]) == {
        "site": "MTY",
        "dry_run": True,
    }


def test_chunk_splits_only_standalone_stage_separators():
    assert chunk(["one", "--value", "a-b", "-", "two"]) == [
        ["one", "--value", "a-b"],
        ["two"],
    ]
