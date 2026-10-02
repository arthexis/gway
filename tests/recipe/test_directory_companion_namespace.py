from gway import Gateway
from gway.recipe.runtime import execute_recipe, ingest_companion


def _directory_recipe(tmp_path):
    recipe_dir = tmp_path / "demo"
    recipe_dir.mkdir()
    recipe = recipe_dir / "__main__.rx"
    recipe.write_text("demo report\n", encoding="utf-8")
    (recipe_dir / "__main__.py").write_text(
        "def report():\n"
        "    return 'directory-companion-ok'\n",
        encoding="utf-8",
    )
    return recipe


def test_directory_companion_uses_public_recipe_namespace(tmp_path):
    recipe = _directory_recipe(tmp_path)
    runtime = Gateway()

    wrapped = ingest_companion(runtime, recipe)

    assert wrapped
    assert runtime.ops.resolve("demo.report") is not None
    assert runtime.ops.resolve("__main__.report") is None


def test_directory_recipe_can_call_its_companion_child(tmp_path):
    recipe = _directory_recipe(tmp_path)
    runtime = Gateway()

    _, result = execute_recipe(runtime, recipe)

    assert result == "directory-companion-ok"
