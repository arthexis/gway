import os

import pytest


def test_recipe_ingests_same_stem_companion_before_resolution(
    gateway, recipe_factory
):
    recipe = recipe_factory(
        name="deploy",
        body="deploy prepare charger\n",
        companion=(
            "def prepare(name):\n"
            "    return f'prepared:{name}'\n"
        ),
    )

    assert gateway(recipe) == "prepared:charger"
    assert gateway.ops.resolve("deploy.prepare") is not None


def test_companion_is_resolved_from_recipe_directory_not_cwd(
    gateway, recipe_factory, tmp_path, monkeypatch
):
    root = tmp_path / "recipes"
    recipe = recipe_factory(
        name="status",
        root=root,
        body="status read\n",
        companion="def read():\n    return 'recipe-dir'\n",
    )
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "status.py").write_text(
        "def read():\n    return 'cwd'\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(elsewhere)

    assert gateway(recipe) == "recipe-dir"


def test_companion_is_ingested_once_per_gateway(
    gateway, recipe_factory, tmp_path
):
    marker = tmp_path / "imports.txt"
    recipe = recipe_factory(
        name="once",
        body="once run\n",
        companion=(
            "from pathlib import Path\n"
            f"_marker = Path({str(marker)!r})\n"
            "_marker.write_text("
            "_marker.read_text() + 'x' if _marker.exists() else 'x'"
            ")\n"
            "def run():\n"
            "    return 'ok'\n"
        ),
    )

    assert gateway(recipe) == "ok"
    assert gateway(recipe) == "ok"
    assert marker.read_text(encoding="utf-8") == "x"


def test_nested_recipe_loads_its_own_companion(gateway, recipe_factory):
    inner = recipe_factory(
        "inner",
        "inner ping\n",
        companion="def ping():\n    return 'pong'\n",
    )
    outer = recipe_factory("outer", "./inner.rx\n")

    assert gateway(outer) == "pong"
    assert inner.is_file()


def test_failed_companion_import_prevents_recipe_execution(
    gateway, recipe_factory
):
    recipe = recipe_factory(
        name="broken",
        body="clear\n",
        companion="raise RuntimeError('companion boom')\n",
    )

    with pytest.raises(RuntimeError, match="companion boom"):
        gateway(recipe)


def test_required_companion_namespace_is_hidden_until_require_passes(
    gateway, recipe_factory, required_runtime
):
    recipe = recipe_factory(
        body="demo ping\nrequire placeholder\n",
        companion="def ping():\n    return 'pong'\n",
    )

    with pytest.raises(LookupError, match="Unable to resolve operation"):
        gateway(recipe)

    assert gateway.ops.resolve("demo.ping") is None


def test_require_unlocks_managed_companion_namespace(
    gateway, recipe_factory, required_runtime
):
    recipe = recipe_factory(
        body="require placeholder\ndemo ping hello\n",
        companion=(
            "def ping(value='pong'):\n"
            "    return value\n"
        ),
    )

    assert gateway(recipe) == "hello"
    assert gateway.ops.resolve("demo.ping") is None


def test_require_can_unlock_companion_in_same_pipeline(
    gateway, recipe_factory, required_runtime
):
    recipe = recipe_factory(
        body="require placeholder - demo ping\n",
        companion="def ping():\n    return 'pong'\n",
    )

    assert gateway(recipe) == "pong"


def test_managed_companion_runs_in_separate_process(
    gateway, recipe_factory, required_runtime
):
    recipe = recipe_factory(
        body="require placeholder\ndemo pid\n",
        companion=(
            "import os\n"
            "def pid():\n"
            "    return os.getpid()\n"
        ),
    )

    assert gateway(recipe) != os.getpid()
