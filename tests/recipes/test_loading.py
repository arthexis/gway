import pytest

from gway.console import load_recipe


def test_recipe_loads_explicit_path(tmp_path, token_values):
    path = tmp_path / "simple.rx"
    path.write_text("echo hello\n", encoding="utf-8")
    commands, comments = load_recipe(path)
    assert token_values(commands[0]) == ["echo", "hello"]
    assert comments == []


def test_multiline_flags_extend_previous_operation(tmp_path, token_values):
    path = tmp_path / "flags.rx"
    path.write_text(
        "create charger\n"
        "    --serial ABC\n"
        "    --limit 32\n",
        encoding="utf-8",
    )
    commands, _ = load_recipe(path)
    assert token_values(commands[0]) == [
        "create", "charger", "--serial", "ABC", "--limit", "32"
    ]


def test_blank_lines_and_comments_do_not_create_operations(tmp_path, token_values):
    path = tmp_path / "comments.rx"
    path.write_text(
        "# heading\n\n"
        "echo one\n"
        "# explanation\n",
        encoding="utf-8",
    )
    commands, comments = load_recipe(path)
    assert token_values(commands[0]) == ["echo", "one"]
    assert comments == ["# heading", "# explanation"]


def test_missing_recipe_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_recipe(tmp_path / "missing.rx")


def test_no_implicit_bundled_recipe_lookup(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(FileNotFoundError):
        load_recipe("named-recipe")
