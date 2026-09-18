from gway.console import load_recipe


def test_python_fence_is_plain_recipe_text_not_executed(tmp_path, token_values):
    path = tmp_path / "python.rx"
    path.write_text("result = dangerous()\n", encoding="utf-8")
    commands, _ = load_recipe(path)
    assert token_values(commands[0]) == ["result", "=", "dangerous()"]
