from gway.recipes import load_recipe


def test_section_selection(tmp_path, token_values):
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
