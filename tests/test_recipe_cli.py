from __future__ import annotations

from pathlib import Path

from gway import bootstrap


def test_recipe_help_is_first_class(capsys) -> None:
    assert bootstrap.main(["recipe", "--help"]) == 0
    output = capsys.readouterr().out
    assert "gway recipe" in output
    assert "FILE.rx" in output


def test_recipe_cli_runs_file_and_renders_each_result(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    recipe = tmp_path / "sample.rx"
    recipe.write_text("ignored by stub\n", encoding="utf-8")
    calls: list[str] = []

    def fake_run_recipe(path, dispatcher, *, interactive=False, on_result=None):
        calls.append(str(path))
        assert interactive is False
        assert on_result is not None
        on_result({"first": "value"})
        on_result("done")
        return "done"

    monkeypatch.setattr("gway.recipe.run_recipe", fake_run_recipe)

    assert bootstrap.main(["recipe", str(recipe)]) == 0
    assert calls == [str(recipe)]
    assert capsys.readouterr().out == "first: value\ndone\n"


def test_recipe_cli_forwards_interactive_flag(
    tmp_path: Path,
    monkeypatch,
) -> None:
    recipe = tmp_path / "sample.rx"
    recipe.write_text("ignored by stub\n", encoding="utf-8")
    seen: list[bool] = []

    def fake_run_recipe(path, dispatcher, *, interactive=False, on_result=None):
        seen.append(interactive)
        return None

    monkeypatch.setattr("gway.recipe.run_recipe", fake_run_recipe)

    assert bootstrap.main(["recipe", "-i", str(recipe)]) == 0
    assert seen == [True]


def test_recipe_cli_accepts_interactive_before_command(
    tmp_path: Path,
    monkeypatch,
) -> None:
    recipe = tmp_path / "sample.rx"
    recipe.write_text("ignored by stub\n", encoding="utf-8")
    seen: list[bool] = []

    def fake_run_recipe(path, dispatcher, *, interactive=False, on_result=None):
        seen.append(interactive)
        return None

    monkeypatch.setattr("gway.recipe.run_recipe", fake_run_recipe)

    assert bootstrap.main(["-i", "recipe", str(recipe)]) == 0
    assert seen == [True]
