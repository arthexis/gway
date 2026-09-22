import pytest

from gway.recipe import load_recipe


def test_recipe_loads_explicit_path(recipe_factory, token_values):
    path = recipe_factory(body="echo hello\n")
    commands, comments = load_recipe(path)

    assert token_values(commands[0]) == ["echo", "hello"]
    assert comments == []


def test_multiline_flags_extend_previous_operation(recipe_factory, token_values):
    path = recipe_factory(
        body=(
            "create charger\n"
            "    --serial ABC\n"
            "    --limit 32\n"
        )
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


def test_trailing_double_dash_continues_with_positional_line(
    recipe_factory, token_values
):
    path = recipe_factory(
        body=(
            "curl --fail --silent --show-error --\n"
            "https://example.com/health/\n"
            "echo done\n"
        )
    )
    commands, _ = load_recipe(path)

    assert token_values(commands[0]) == [
        "curl",
        "--fail",
        "--silent",
        "--show-error",
        "--",
        "https://example.com/health/",
    ]
    assert token_values(commands[1]) == ["echo", "done"]


def test_standalone_double_dash_continues_with_positional_line(
    recipe_factory, token_values
):
    path = recipe_factory(
        body=(
            "service install\n"
            "--system\n"
            "--\n"
            "arthexis web\n"
        )
    )
    commands, _ = load_recipe(path)

    assert token_values(commands[0]) == [
        "service",
        "install",
        "--system",
        "--",
        "arthexis",
        "web",
    ]


def test_literal_double_dash_does_not_continue_next_line(
    recipe_factory, token_values
):
    path = recipe_factory(body="echo '--'\necho next\n")
    commands, _ = load_recipe(path)

    assert token_values(commands[0]) == ["echo", "--"]
    assert token_values(commands[1]) == ["echo", "next"]


def test_blank_lines_and_comments_do_not_create_operations(
    recipe_factory, token_values
):
    path = recipe_factory(
        body="# heading\n\necho one\n# explanation\n"
    )
    commands, comments = load_recipe(path)

    assert token_values(commands[0]) == ["echo", "one"]
    assert comments == ["# heading", "# explanation"]


def test_section_selection(recipe_factory, token_values):
    path = recipe_factory(
        body="# First\necho one\n# Second\necho two\n"
    )
    commands, _ = load_recipe(path, section="Second")

    assert len(commands) == 1
    assert token_values(commands[0]) == ["echo", "two"]


def test_python_fence_is_plain_recipe_text_not_executed(
    recipe_factory, token_values
):
    path = recipe_factory(body="result = dangerous()\n")
    commands, _ = load_recipe(path)

    assert token_values(commands[0]) == ["result", "=", "dangerous()"]


def test_missing_recipe_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_recipe(tmp_path / "missing.rx")


def test_no_implicit_bundled_recipe_lookup(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    with pytest.raises(FileNotFoundError):
        load_recipe("named-recipe")
