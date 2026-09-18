import pytest

from gway.console import Token, load_recipe


def token_values(command):
    return [token.value if isinstance(token, Token) else token for token in command["tokens"]]


def test_recipe_loads_explicit_path(tmp_path):
    path = tmp_path / "simple.rx"
    path.write_text("echo hello\n", encoding="utf-8")

    commands, comments = load_recipe(path)
    assert token_values(commands[0]) == ["echo", "hello"]
    assert comments == []


def test_multiline_flags_extend_previous_operation(tmp_path):
    path = tmp_path / "flags.rx"
    path.write_text(
        "create charger\n"
        "    --serial ABC\n"
        "    --limit 32\n",
        encoding="utf-8",
    )

    commands, _ = load_recipe(path)
    assert token_values(commands[0]) == [
        "create",
        "charger",
        "--serial",
        "ABC",
        "--limit",
        "32",
    ]


def test_blank_lines_and_comments_do_not_create_operations(tmp_path):
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


def test_section_selection(tmp_path):
    path = tmp_path / "sections.rx"
    path.write_text(
        "# First\n"
        "echo one\n"
        "# Second\n"
        "echo two\n",
        encoding="utf-8",
    )

    commands, _ = load_recipe(path, section="Second")
    assert len(commands) == 1
    assert token_values(commands[0]) == ["echo", "two"]


def test_missing_recipe_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_recipe(tmp_path / "missing.rx")


def test_no_implicit_bundled_recipe_lookup(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(FileNotFoundError):
        load_recipe("named-recipe")


def test_python_fence_is_plain_recipe_text_not_executed(tmp_path):
    path = tmp_path / "python.rx"
    path.write_text("result = dangerous()\n", encoding="utf-8")
    commands, _ = load_recipe(path)
    assert token_values(commands[0]) == ["result", "=", "dangerous()"]
