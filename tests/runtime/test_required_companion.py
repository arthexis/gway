import os
from pathlib import Path
import sys

import pytest

from gway.recipes import execute_recipe


@pytest.fixture
def managed_runtime(monkeypatch, tmp_path):
    uv = tmp_path / "uv"
    sync_calls = []

    monkeypatch.setattr("gway.uv.ensure_uv", lambda **kwargs: uv)

    def sync(environment, executable, requirements):
        sync_calls.append((environment, executable, tuple(requirements)))
        return Path(sys.executable)

    monkeypatch.setattr(
        "gway.recipe_environment.sync_python_environment",
        sync,
    )
    monkeypatch.setattr(
        "gway.recipe_environment.environment_python",
        lambda environment: Path(sys.executable),
    )
    return sync_calls


def test_require_preflight_happens_before_first_statement(
    gateway, tmp_path, managed_runtime
):
    recipe = tmp_path / "demo.rx"
    recipe.write_text(
        "clear\n"
        "require fastmcp\n",
        encoding="utf-8",
    )

    execute_recipe(gateway, recipe)

    assert len(managed_runtime) == 1
    _, _, requirements = managed_runtime[0]
    assert requirements == ("fastmcp",)


def test_required_companion_namespace_is_hidden_until_require_passes(
    gateway, tmp_path, managed_runtime
):
    recipe = tmp_path / "demo.rx"
    companion = tmp_path / "demo.py"
    companion.write_text(
        "def ping():\n"
        "    return 'pong'\n",
        encoding="utf-8",
    )
    recipe.write_text(
        "demo ping\n"
        "require placeholder\n",
        encoding="utf-8",
    )

    with pytest.raises(LookupError, match="Unable to resolve operation"):
        execute_recipe(gateway, recipe)

    assert gateway.ops.resolve("demo.ping") is None


def test_require_unlocks_managed_companion_namespace(
    gateway, tmp_path, managed_runtime
):
    recipe = tmp_path / "demo.rx"
    companion = tmp_path / "demo.py"
    companion.write_text(
        "def ping(value='pong'):\n"
        "    return value\n",
        encoding="utf-8",
    )
    recipe.write_text(
        "require placeholder\n"
        "demo ping hello\n",
        encoding="utf-8",
    )

    _, result = execute_recipe(gateway, recipe)

    assert result == "hello"
    assert gateway.ops.resolve("demo.ping") is None


def test_require_can_unlock_companion_in_same_pipeline(
    gateway, tmp_path, managed_runtime
):
    recipe = tmp_path / "demo.rx"
    companion = tmp_path / "demo.py"
    companion.write_text(
        "def ping():\n"
        "    return 'pong'\n",
        encoding="utf-8",
    )
    recipe.write_text(
        "require placeholder - demo ping\n",
        encoding="utf-8",
    )

    _, result = execute_recipe(gateway, recipe)

    assert result == "pong"


def test_all_requirements_are_preflighted_even_when_declared_late(
    gateway, tmp_path, managed_runtime
):
    recipe = tmp_path / "demo.rx"
    recipe.write_text(
        "clear\n"
        "require alpha\n"
        "clear\n"
        "require beta gamma --python\n",
        encoding="utf-8",
    )

    execute_recipe(gateway, recipe)

    assert len(managed_runtime) == 1
    _, _, requirements = managed_runtime[0]
    assert requirements == ("alpha", "beta", "gamma")


def test_managed_companion_runs_in_separate_process(
    gateway, tmp_path, managed_runtime
):
    recipe = tmp_path / "demo.rx"
    companion = tmp_path / "demo.py"
    companion.write_text(
        "import os\n"
        "def pid():\n"
        "    return os.getpid()\n",
        encoding="utf-8",
    )
    recipe.write_text(
        "require placeholder\n"
        "demo pid\n",
        encoding="utf-8",
    )

    _, result = execute_recipe(gateway, recipe)

    assert result != os.getpid()
