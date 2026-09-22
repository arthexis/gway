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
