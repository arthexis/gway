from gway import log as gway_log
from gway.gateway import Gateway
from gway.recipe import execute_recipe


def test_recipe_execution_indexes_recipe_launchable(tmp_path):
    recipe = tmp_path / "worker.rx"
    recipe.write_text("", encoding="utf-8")
    runtime = Gateway()

    execute_recipe(runtime, recipe)

    launchable = runtime.launchables["worker"]
    assert launchable.kind == "recipe"
    assert launchable.target == recipe.resolve()
    assert launchable.command == (
        "{python}",
        "-m",
        "gway",
        str(recipe.resolve()),
    )


def test_recipe_execution_scopes_log_identity(tmp_path):
    recipe = tmp_path / "deploy.rx"
    recipe.write_text("capture\n", encoding="utf-8")
    runtime = Gateway()
    runtime.wrap("capture", gway_log._current_source)

    _, output = execute_recipe(runtime, recipe)

    assert output == "recipe/deploy"
    assert gway_log._current_source() == "gway"


def test_recipe_preserves_published_observation_context_between_statements(tmp_path):
    recipe = tmp_path / "observe.rx"
    recipe.write_text(
        "observe --section first -- probe one\n"
        "observe --section second -- probe two\n"
        "observation collect first second\n",
        encoding="utf-8",
    )
    runtime = Gateway()
    runtime.wrap("probe", lambda value, *, mutate=False: value)

    _, output = execute_recipe(runtime, recipe)

    assert output["first"]["status"] == "ok"
    assert output["first"]["result"] == "one"
    assert output["second"]["status"] == "ok"
    assert output["second"]["result"] == "two"
    assert output["health"]["sections"] == {"first": "ok", "second": "ok"}


def test_recipe_execution_registers_durable_log_source(tmp_path, monkeypatch):
    from gway.logs.registry import recipe_sources

    recipe = tmp_path / "watchtower.rx"
    recipe.write_text("", encoding="utf-8")
    runtime = Gateway()
    monkeypatch.setattr(runtime, "data_root", lambda *args, **kwargs: tmp_path / "data")

    execute_recipe(runtime, recipe)

    assert [source.identity for source in recipe_sources(tmp_path / "data")] == [
        "recipe/watchtower"
    ]
