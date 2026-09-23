import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from gway.install.model import Installation
from gway.recipe.environment import (
    environment_python,
    recipe_environment,
    sync_python_environment,
)


def _runtime(**installed):
    return SimpleNamespace(_installed=installed)


def _fake_uv_run(calls, environment):
    def run(argv, **kwargs):
        calls.append((list(argv), dict(kwargs)))
        if argv[1] == "venv":
            python = environment_python(environment)
            python.parent.mkdir(parents=True, exist_ok=True)
            python.write_text("", encoding="utf-8")
        elif argv[1:3] == ["pip", "compile"]:
            source = Path(argv[5])
            output = Path(argv[argv.index("--output-file") + 1])
            output.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        return SimpleNamespace(returncode=0)

    return run


def test_local_environment_uses_external_data_root(
    monkeypatch, recipe_factory, tmp_path
):
    data = tmp_path / "data"
    source = tmp_path / "source"
    recipe = recipe_factory(root=source, body="clear\n")
    monkeypatch.setenv("GWAY_DATA_DIR", str(data))

    environment = recipe_environment(_runtime(), recipe)

    assert environment.recipe == recipe.resolve()
    assert environment.scope == "user"
    assert environment.root.parent == data.resolve() / "recipes"
    assert environment.venv == environment.root / "venv"
    assert environment.metadata == environment.root / "metadata.json"
    assert environment.requirements_file == environment.root / "requirements.txt"
    assert not environment.root.exists()
    assert list(source.iterdir()) == [recipe]


def test_same_physical_recipe_keeps_environment_identity(
    monkeypatch, recipe_factory, tmp_path
):
    monkeypatch.setenv("GWAY_DATA_DIR", str(tmp_path / "data"))
    recipe = recipe_factory(
        root=tmp_path / "tree" / "nested",
        body="clear\n",
    )
    runtime = _runtime()

    direct = recipe_environment(runtime, recipe)
    relative = recipe_environment(runtime, recipe.parent / "." / recipe.name)

    assert direct.key == relative.key
    assert direct.identity == relative.identity
    assert direct.root == relative.root


def test_managed_environment_uses_source_and_relative_path(
    monkeypatch, recipe_factory, tmp_path
):
    monkeypatch.setenv("GWAY_DATA_DIR", str(tmp_path / "data"))
    installed = tmp_path / "projects" / "demo"
    recipe = recipe_factory(
        name="serve",
        root=installed / "sampler" / "mcp",
        body="clear\n",
    )
    installation = Installation(
        name="demo",
        source="https://github.com/example/demo.git",
        install_path=installed,
        scope="user",
        requested_ref="main",
        resolved_revision="abc123",
    )

    environment = recipe_environment(_runtime(demo=installation), recipe)

    assert environment.identity == (
        "managed:https://github.com/example/demo.git:sampler/mcp/serve.rx"
    )
    assert environment.source == installation.source
    assert environment.relative_path == Path("sampler/mcp/serve.rx")
    assert environment.resolved_revision == "abc123"


def test_managed_revision_change_reuses_environment(
    monkeypatch, recipe_factory, tmp_path
):
    monkeypatch.setenv("GWAY_DATA_DIR", str(tmp_path / "data"))
    installed = tmp_path / "projects" / "demo"
    recipe = recipe_factory(
        name="mcp",
        root=installed / "sampler",
        body="clear\n",
    )

    def environment(revision):
        installation = Installation(
            name="demo",
            source="https://github.com/example/demo.git",
            install_path=installed,
            resolved_revision=revision,
        )
        return recipe_environment(_runtime(demo=installation), recipe)

    first = environment("abc123")
    second = environment("def456")

    assert first.key == second.key
    assert first.root == second.root
    assert first.resolved_revision == "abc123"
    assert second.resolved_revision == "def456"


def test_recipe_frame_exposes_environment_identity(
    gateway, recipe_factory, monkeypatch, tmp_path
):
    monkeypatch.setenv("GWAY_DATA_DIR", str(tmp_path / "data"))

    def probe():
        return gateway._recipe_frames[-1].environment

    gateway.wrap("environment probe", probe)
    recipe = recipe_factory(body="environment probe\n")

    environment = gateway(recipe)

    assert environment.recipe == recipe.resolve()
    assert environment.root.parent == (tmp_path / "data" / "recipes").resolve()


def test_sync_creates_venv_and_persists_requirements(
    monkeypatch, recipe_factory, tmp_path
):
    monkeypatch.setenv("GWAY_DATA_DIR", str(tmp_path / "data"))
    source = tmp_path / "source"
    recipe = recipe_factory(root=source, body="require fastmcp\n")
    environment = recipe_environment(_runtime(), recipe)
    calls = []
    monkeypatch.setattr(
        "gway.recipe.environment.subprocess.run",
        _fake_uv_run(calls, environment),
    )

    python = sync_python_environment(
        environment,
        tmp_path / "uv",
        ["fastmcp", "cryptography>=42"],
    )

    assert python == environment_python(environment)
    assert environment.requirements_file.read_text(encoding="utf-8") == (
        "fastmcp\ncryptography>=42\n"
    )
    metadata = json.loads(environment.metadata.read_text(encoding="utf-8"))
    assert metadata["requirements"]["python"] == ["fastmcp", "cryptography>=42"]
    assert [call[0][1:3] for call in calls] == [
        ["venv", str(environment.venv)],
        ["pip", "compile"],
        ["pip", "sync"],
    ]
    assert (environment.root / "requirements.lock.txt").read_text(
        encoding="utf-8"
    ) == "fastmcp\ncryptography>=42\n"
    assert list(source.iterdir()) == [recipe]


def test_sync_reconciles_requirements_when_metadata_is_unchanged(
    monkeypatch, recipe_factory, tmp_path
):
    monkeypatch.setenv("GWAY_DATA_DIR", str(tmp_path / "data"))
    recipe = recipe_factory(body="require fastmcp\n")
    environment = recipe_environment(_runtime(), recipe)
    calls = []
    monkeypatch.setattr(
        "gway.recipe.environment.subprocess.run",
        _fake_uv_run(calls, environment),
    )
    sync_python_environment(environment, tmp_path / "uv", ["fastmcp"])
    calls.clear()

    assert sync_python_environment(
        environment,
        tmp_path / "uv",
        ["fastmcp"],
    ) == environment_python(environment)

    assert len(calls) == 2
    compile_argv, compile_kwargs = calls[0]
    sync_argv, sync_kwargs = calls[1]
    assert compile_argv[:3] == [str(tmp_path / "uv"), "pip", "compile"]
    assert compile_argv[-2:] == [
        "--output-file",
        str(environment.root / "requirements.lock.txt"),
    ]
    assert compile_kwargs["check"] is True
    assert sync_argv[:3] == [str(tmp_path / "uv"), "pip", "sync"]
    assert sync_argv[-1] == str(environment.root / "requirements.lock.txt")
    assert sync_kwargs["check"] is True


def test_sync_changed_requirements_reuses_venv(
    monkeypatch, recipe_factory, tmp_path
):
    monkeypatch.setenv("GWAY_DATA_DIR", str(tmp_path / "data"))
    recipe = recipe_factory(body="require fastmcp\n")
    environment = recipe_environment(_runtime(), recipe)
    calls = []
    monkeypatch.setattr(
        "gway.recipe.environment.subprocess.run",
        _fake_uv_run(calls, environment),
    )

    sync_python_environment(environment, tmp_path / "uv", ["fastmcp"])
    calls.clear()
    sync_python_environment(
        environment,
        tmp_path / "uv",
        ["fastmcp", "cryptography"],
    )

    assert len(calls) == 2
    compile_argv, compile_kwargs = calls[0]
    sync_argv, sync_kwargs = calls[1]
    assert compile_argv[:3] == [str(tmp_path / "uv"), "pip", "compile"]
    assert compile_argv[-2:] == [
        "--output-file",
        str(environment.root / "requirements.lock.txt"),
    ]
    assert compile_kwargs["check"] is True
    assert sync_argv[:3] == [str(tmp_path / "uv"), "pip", "sync"]
    assert sync_argv[-1] == str(environment.root / "requirements.lock.txt")
    assert sync_kwargs["check"] is True


def test_sync_recreates_missing_venv(
    monkeypatch, recipe_factory, tmp_path
):
    monkeypatch.setenv("GWAY_DATA_DIR", str(tmp_path / "data"))
    recipe = recipe_factory(body="require fastmcp\n")
    environment = recipe_environment(_runtime(), recipe)
    calls = []
    monkeypatch.setattr(
        "gway.recipe.environment.subprocess.run",
        _fake_uv_run(calls, environment),
    )

    sync_python_environment(environment, tmp_path / "uv", ["fastmcp"])
    environment_python(environment).unlink()
    calls.clear()
    sync_python_environment(environment, tmp_path / "uv", ["fastmcp"])

    assert [call[0][1] for call in calls] == ["venv", "pip", "pip"]
    assert [call[0][2] for call in calls[1:]] == ["compile", "sync"]


def test_sync_rejects_newline_package_specs(
    monkeypatch, recipe_factory, tmp_path
):
    monkeypatch.setenv("GWAY_DATA_DIR", str(tmp_path / "data"))
    recipe = recipe_factory(body="clear\n")
    environment = recipe_environment(_runtime(), recipe)

    with pytest.raises(ValueError, match="cannot contain newlines"):
        sync_python_environment(
            environment,
            tmp_path / "uv",
            ["fastmcp\nmalicious"],
        )



def test_set_env_is_visible_to_following_recipe_operations_and_restored(
    gateway, recipe_factory, monkeypatch
):
    monkeypatch.setenv("GWAY_SCOPED_TEST", "parent")

    def probe():
        import os

        return os.environ.get("GWAY_SCOPED_TEST")

    gateway.wrap("environment probe", probe)
    recipe = recipe_factory(
        body=(
            "set env GWAY_SCOPED_TEST recipe\n"
            "environment probe\n"
        )
    )

    assert gateway(recipe) == "recipe"
    assert probe() == "parent"


def test_set_env_child_recipe_inherits_and_nested_override_does_not_leak(
    gateway, recipe_factory, monkeypatch, tmp_path
):
    monkeypatch.setenv("GWAY_SCOPED_TEST", "parent")

    seen = []

    def probe():
        import os

        value = os.environ.get("GWAY_SCOPED_TEST")
        seen.append(value)
        return value

    gateway.wrap("environment probe", probe)
    root = tmp_path / "recipes"
    recipe_factory(
        name="child",
        root=root,
        body=(
            "environment probe\n"
            "set env GWAY_SCOPED_TEST child\n"
            "environment probe\n"
        ),
    )
    parent = recipe_factory(
        name="parent",
        root=root,
        body=(
            "set env GWAY_SCOPED_TEST outer\n"
            "./child.rx\n"
            "environment probe\n"
        ),
    )

    gateway(parent)

    assert seen == ["outer", "child", "outer"]
    assert probe() == "parent"


def test_clear_env_is_scoped_and_restores_parent_value(
    gateway, recipe_factory, monkeypatch
):
    monkeypatch.setenv("GWAY_SCOPED_TEST", "parent")

    def probe():
        import os

        return os.environ.get("GWAY_SCOPED_TEST")

    gateway.wrap("environment probe", probe)
    recipe = recipe_factory(
        body=(
            "clear env GWAY_SCOPED_TEST\n"
            "environment probe\n"
        )
    )

    assert gateway(recipe) is None
    assert probe() == "parent"


def test_set_env_requires_active_recipe(gateway):
    with pytest.raises(RuntimeError, match="only available during recipe execution"):
        gateway("set env GWAY_SCOPED_TEST value")



def test_set_env_restores_parent_value_after_recipe_failure(
    gateway, recipe_factory, monkeypatch
):
    monkeypatch.setenv("GWAY_SCOPED_TEST", "parent")

    def fail():
        raise RuntimeError("boom")

    gateway.wrap("environment fail", fail)
    recipe = recipe_factory(
        body=(
            "set env GWAY_SCOPED_TEST recipe\n"
            "environment fail\n"
        )
    )

    with pytest.raises(RuntimeError, match="boom"):
        gateway(recipe)

    assert gateway("env GWAY_SCOPED_TEST") == "parent"


def test_set_env_is_available_in_spaced_and_dashed_forms(
    gateway, recipe_factory, monkeypatch
):
    monkeypatch.delenv("GWAY_SCOPED_TEST", raising=False)

    def probe():
        import os

        return os.environ.get("GWAY_SCOPED_TEST")

    gateway.wrap("environment probe", probe)
    spaced = recipe_factory(
        name="spaced",
        body=(
            "set env GWAY_SCOPED_TEST spaced\n"
            "environment probe\n"
        ),
    )
    dashed = recipe_factory(
        name="dashed",
        body=(
            "set-env GWAY_SCOPED_TEST dashed\n"
            "environment probe\n"
        ),
    )

    assert gateway(spaced) == "spaced"
    assert gateway(dashed) == "dashed"
    assert gateway("env GWAY_SCOPED_TEST") is None
