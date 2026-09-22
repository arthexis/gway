import json
from types import SimpleNamespace

import pytest

from gway.recipe_environment import (
    environment_python,
    recipe_environment,
    sync_python_environment,
)


def _runtime():
    return SimpleNamespace(_installed={})


def _fake_uv_run(calls, environment):
    def run(argv, **kwargs):
        calls.append((list(argv), dict(kwargs)))
        if argv[1] == "venv":
            python = environment_python(environment)
            python.parent.mkdir(parents=True, exist_ok=True)
            python.write_text("", encoding="utf-8")
        return SimpleNamespace(returncode=0)

    return run


def test_sync_creates_external_venv_and_persists_requirements(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("GWAY_DATA_DIR", str(tmp_path / "data"))
    source = tmp_path / "source"
    source.mkdir()
    recipe = source / "demo.rx"
    recipe.write_text("require fastmcp\n", encoding="utf-8")
    environment = recipe_environment(_runtime(), recipe)
    calls = []
    monkeypatch.setattr(
        "gway.recipe_environment.subprocess.run",
        _fake_uv_run(calls, environment),
    )

    python = sync_python_environment(
        environment,
        tmp_path / "uv",
        ["fastmcp", "cryptography>=42"],
    )

    assert python == environment_python(environment)
    assert environment.venv.is_dir()
    assert environment.requirements_file.read_text(encoding="utf-8") == (
        "fastmcp\ncryptography>=42\n"
    )
    metadata = json.loads(environment.metadata.read_text(encoding="utf-8"))
    assert metadata["requirements"]["python"] == ["fastmcp", "cryptography>=42"]
    assert [call[0][1:3] for call in calls] == [
        ["venv", str(environment.venv)],
        ["pip", "sync"],
    ]
    assert list(source.iterdir()) == [recipe]


def test_sync_is_noop_when_desired_state_and_venv_are_intact(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("GWAY_DATA_DIR", str(tmp_path / "data"))
    recipe = tmp_path / "demo.rx"
    recipe.write_text("require fastmcp\n", encoding="utf-8")
    environment = recipe_environment(_runtime(), recipe)
    first_calls = []
    monkeypatch.setattr(
        "gway.recipe_environment.subprocess.run",
        _fake_uv_run(first_calls, environment),
    )
    sync_python_environment(environment, tmp_path / "uv", ["fastmcp"])

    def forbidden(*args, **kwargs):
        raise AssertionError("uv should not run for unchanged desired state")

    monkeypatch.setattr("gway.recipe_environment.subprocess.run", forbidden)

    assert sync_python_environment(
        environment, tmp_path / "uv", ["fastmcp"]
    ) == environment_python(environment)


def test_sync_changed_requirements_reuses_venv_and_resyncs(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("GWAY_DATA_DIR", str(tmp_path / "data"))
    recipe = tmp_path / "demo.rx"
    recipe.write_text("require fastmcp\n", encoding="utf-8")
    environment = recipe_environment(_runtime(), recipe)
    calls = []
    monkeypatch.setattr(
        "gway.recipe_environment.subprocess.run",
        _fake_uv_run(calls, environment),
    )

    sync_python_environment(environment, tmp_path / "uv", ["fastmcp"])
    calls.clear()
    sync_python_environment(
        environment,
        tmp_path / "uv",
        ["fastmcp", "cryptography"],
    )

    assert len(calls) == 1
    argv, kwargs = calls[0]
    assert argv[:3] == [str(tmp_path / "uv"), "pip", "sync"]
    assert argv[-1] == str(environment.requirements_file)
    assert kwargs["check"] is True
    assert environment.requirements_file.read_text(encoding="utf-8") == (
        "fastmcp\ncryptography\n"
    )


def test_sync_recreates_missing_venv_even_when_metadata_matches(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("GWAY_DATA_DIR", str(tmp_path / "data"))
    recipe = tmp_path / "demo.rx"
    recipe.write_text("require fastmcp\n", encoding="utf-8")
    environment = recipe_environment(_runtime(), recipe)
    calls = []
    monkeypatch.setattr(
        "gway.recipe_environment.subprocess.run",
        _fake_uv_run(calls, environment),
    )
    sync_python_environment(environment, tmp_path / "uv", ["fastmcp"])

    environment_python(environment).unlink()
    calls.clear()
    sync_python_environment(environment, tmp_path / "uv", ["fastmcp"])

    assert [call[0][1] for call in calls] == ["venv", "pip"]


def test_sync_rejects_newline_package_specs(monkeypatch, tmp_path):
    monkeypatch.setenv("GWAY_DATA_DIR", str(tmp_path / "data"))
    recipe = tmp_path / "demo.rx"
    recipe.write_text("clear\n", encoding="utf-8")
    environment = recipe_environment(_runtime(), recipe)

    with pytest.raises(ValueError, match="cannot contain newlines"):
        sync_python_environment(
            environment,
            tmp_path / "uv",
            ["fastmcp\nmalicious"],
        )
