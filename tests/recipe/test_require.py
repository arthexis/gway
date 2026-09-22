import pytest

from gway.recipe import execute_recipe
from gway.recipe.require import collect_recipe_requirements
from gway.tokens import statements, tokenize


def _requirements(text):
    return collect_recipe_requirements(statements(tokenize(text)))


def test_collect_requirements_defaults_to_python():
    assert _requirements("require fastmcp cryptography") == {
        "python": ["fastmcp", "cryptography"]
    }


def test_collect_requirements_accepts_explicit_python_flag():
    assert _requirements("require fastmcp --python") == {
        "python": ["fastmcp"]
    }


def test_collect_requirements_across_recipe_deduplicates_packages():
    statement_list = [
        *statements(tokenize("require fastmcp")),
        *statements(tokenize("require fastmcp cryptography --python")),
    ]

    assert collect_recipe_requirements(statement_list) == {
        "python": ["fastmcp", "cryptography"]
    }


def test_collect_requirements_rejects_missing_packages():
    with pytest.raises(TypeError, match="at least one package"):
        _requirements("require")


def test_require_rejects_use_outside_recipe(gateway):
    with pytest.raises(RuntimeError, match="only available during recipe execution"):
        gateway("require fastmcp")


def test_require_records_packages_on_active_frame(
    gateway, recipe_factory, required_runtime
):
    captured = {}

    def probe():
        captured.update(gateway._recipe_frames[-1].requirements)
        return "ok"

    gateway.wrap("require probe", probe)
    recipe = recipe_factory(
        body="require fastmcp cryptography\nrequire probe\n"
    )

    execute_recipe(gateway, recipe)

    assert captured == {"python": ["fastmcp", "cryptography"]}


def test_require_is_idempotent_within_recipe(
    gateway, recipe_factory, required_runtime
):
    captured = {}

    def probe():
        captured.update(gateway._recipe_frames[-1].requirements)
        return "ok"

    gateway.wrap("require probe", probe)
    recipe = recipe_factory(
        body=(
            "require fastmcp\n"
            "require fastmcp cryptography\n"
            "require probe\n"
        )
    )

    execute_recipe(gateway, recipe)

    assert captured == {"python": ["fastmcp", "cryptography"]}


def test_all_requirements_are_preflighted_before_first_statement(
    gateway, recipe_factory, required_runtime
):
    recipe = recipe_factory(
        body=(
            "clear\n"
            "require alpha\n"
            "clear\n"
            "require beta gamma --python\n"
        )
    )

    execute_recipe(gateway, recipe)

    assert len(required_runtime.sync_calls) == 1
    _, _, requirements = required_runtime.sync_calls[0]
    assert requirements == ("alpha", "beta", "gamma")
