def test_builtin_env_is_ingested_under_gway_root(gateway, monkeypatch):
    monkeypatch.setenv("GWAY_TEST_ENV", "present")

    assert gateway("gway env GWAY_TEST_ENV") == "present"
    assert gateway.ops.resolve("gway.env") is not None


def test_builtin_env_handles_default_missing_and_empty_values(gateway, monkeypatch):
    monkeypatch.delenv("GWAY_MISSING_ENV", raising=False)
    monkeypatch.setenv("GWAY_EMPTY_ENV", "")

    assert gateway("gway env GWAY_MISSING_ENV fallback") == "fallback"
    assert gateway("gway env GWAY_MISSING_ENV") is None
    assert gateway("gway env GWAY_EMPTY_ENV fallback") == ""


def test_builtin_env_reads_current_environment_each_time(gateway, monkeypatch):
    monkeypatch.setenv("GWAY_DYNAMIC_ENV", "first")
    assert gateway("gway env GWAY_DYNAMIC_ENV") == "first"

    monkeypatch.setenv("GWAY_DYNAMIC_ENV", "second")
    assert gateway("gway env GWAY_DYNAMIC_ENV") == "second"


def test_builtin_envs_returns_detached_snapshot(gateway, monkeypatch):
    monkeypatch.setenv("GWAY_SNAPSHOT_ENV", "before")
    snapshot = gateway("gway envs")

    monkeypatch.setenv("GWAY_SNAPSHOT_ENV", "after")

    assert snapshot["GWAY_SNAPSHOT_ENV"] == "before"
    assert snapshot is not __import__("os").environ
    assert gateway("gway envs")["GWAY_SNAPSHOT_ENV"] == "after"


def test_builtin_envs_can_feed_pipeline(gateway, monkeypatch):
    monkeypatch.setenv("GWAY_PIPELINE_ENV", "pipeline")

    def read_value(values, key):
        return values[key]

    gateway.read_value = gateway.wrap("read_value", read_value)

    assert gateway("gway envs - read_value GWAY_PIPELINE_ENV") == "pipeline"


def test_builtins_are_registered_only_under_gway_root(gateway):
    assert gateway.ops.resolve("gway.env") is not None
    assert gateway.ops.resolve("gway.envs") is not None
    assert "env" not in gateway.__dict__
    assert "envs" not in gateway.__dict__


def test_builtin_toml_default_operation_parses_text(gateway):
    assert gateway.ops.resolve("gway.toml") is None

    result = gateway("gway toml", 'name = "gway"\n[tool]\nenabled = true')

    assert result == {"name": "gway", "tool": {"enabled": True}}
    assert gateway.ops.resolve("gway.toml") is not None


def test_builtin_toml_loads_subject_parses_text(gateway):
    assert gateway("gway toml loads", "answer = 42") == {"answer": 42}


def test_builtin_toml_load_subject_reads_path(gateway, tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('site = "MTY"\n', encoding="utf-8")

    assert gateway("gway toml load", str(path)) == {"site": "MTY"}


def test_builtin_toml_routes_to_version_backend():
    import sys

    import gway.toml as gway_toml

    expected = "tomllib" if sys.version_info >= (3, 11) else "tomli"
    assert gway_toml._backend().__name__ == expected
