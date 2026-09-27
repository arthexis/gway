import pytest

from gway import Gateway
from gway.recipe.validation import RecipeValidationError


def test_recipe_check_validates_tree_without_execution(tmp_path):
    root = tmp_path / "recipes"
    root.mkdir()
    (root / "child.rx").write_text("help\n", encoding="utf-8")
    (root / "parent.rx").write_text("./child.rx\nhelp install\n", encoding="utf-8")

    result = Gateway()(f"recipe check {root}")

    assert result["recipes"] == 2
    assert result["errors"] == 0


def test_recipe_check_rejects_missing_child_recipe(tmp_path):
    recipe = tmp_path / "broken.rx"
    recipe.write_text("./missing.rx\n", encoding="utf-8")

    with pytest.raises(RecipeValidationError, match="child recipe does not exist"):
        Gateway()(f"recipe check {recipe}")


def test_recipe_check_rejects_invalid_repeat_controls(tmp_path):
    recipe = tmp_path / "broken.rx"
    recipe.write_text(
        "help\nrepeat --until true --while false --max 2\n",
        encoding="utf-8",
    )

    with pytest.raises(RecipeValidationError, match="cannot combine --while and --until"):
        Gateway()(f"recipe check {recipe}")


def test_recipe_check_compiles_companion_python(tmp_path):
    recipe = tmp_path / "broken.rx"
    recipe.write_text("help\n", encoding="utf-8")
    recipe.with_suffix(".py").write_text("def broken(:\n", encoding="utf-8")

    with pytest.raises(RecipeValidationError, match="invalid companion Python"):
        Gateway()(f"recipe check {recipe}")


def test_recipe_check_reports_unresolved_dynamic_operation_as_warning(tmp_path):
    recipe = tmp_path / "dynamic.rx"
    recipe.write_text("future external operation --flag value\n", encoding="utf-8")

    result = Gateway()(f"recipe check {recipe}")

    assert result["errors"] == 0
    assert result["warnings"] == 1
    assert "not statically resolvable" in result["findings"][0]


@pytest.mark.parametrize(
    "body",
    [
        "help\ncheck --unless true\n",
        "help\ncheck --rollback deploy\n",
        "help\ncheck nonsense\n",
        "help\ncheck --true --unless false --unless true\n",
    ],
)
def test_recipe_check_rejects_malformed_check_controls(tmp_path, body):
    recipe = tmp_path / "broken.rx"
    recipe.write_text(body, encoding="utf-8")

    with pytest.raises(RecipeValidationError):
        Gateway()(f"recipe check {recipe}")


def test_recipe_check_rejects_supported_missing_explicit_path_forms(tmp_path):
    recipe = tmp_path / "broken.rx"
    recipe.write_text("subdir/missing.rx\n", encoding="utf-8")

    with pytest.raises(RecipeValidationError, match="child recipe does not exist"):
        Gateway()(f"recipe check {recipe}")
