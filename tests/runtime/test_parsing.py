from gway.console import parse_recipe_context
from gway.tokens import chunk


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
