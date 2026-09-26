from pathlib import Path
import sys

from gway.console import cli_main


def test_builtin_env_is_ingested_at_command_root(gateway, monkeypatch):
    monkeypatch.setenv("GWAY_TEST_ENV", "present")

    assert gateway("env GWAY_TEST_ENV") == "present"
    assert gateway.ops.resolve("env") is not None


def test_builtin_env_handles_default_missing_and_empty_values(gateway, monkeypatch):
    monkeypatch.delenv("GWAY_MISSING_ENV", raising=False)
    monkeypatch.setenv("GWAY_EMPTY_ENV", "")

    assert gateway("env GWAY_MISSING_ENV fallback") == "fallback"
    assert gateway("env GWAY_MISSING_ENV") is None
    assert gateway("env GWAY_EMPTY_ENV fallback") == ""


def test_builtin_env_reads_current_environment_each_time(gateway, monkeypatch):
    monkeypatch.setenv("GWAY_DYNAMIC_ENV", "first")
    assert gateway("env GWAY_DYNAMIC_ENV") == "first"

    monkeypatch.setenv("GWAY_DYNAMIC_ENV", "second")
    assert gateway("env GWAY_DYNAMIC_ENV") == "second"


def test_builtin_envs_returns_detached_snapshot(gateway, monkeypatch):
    monkeypatch.setenv("GWAY_SNAPSHOT_ENV", "before")
    snapshot = gateway("envs")

    monkeypatch.setenv("GWAY_SNAPSHOT_ENV", "after")

    assert snapshot["GWAY_SNAPSHOT_ENV"] == "before"
    assert snapshot is not __import__("os").environ
    assert gateway("envs")["GWAY_SNAPSHOT_ENV"] == "after"


def test_builtin_envs_can_feed_pipeline(gateway, monkeypatch):
    monkeypatch.setenv("GWAY_PIPELINE_ENV", "pipeline")

    def read_value(values, key):
        return values[key]

    gateway.read_value = gateway.wrap("read_value", read_value)

    assert gateway("envs - read_value GWAY_PIPELINE_ENV") == "pipeline"


def test_builtins_are_registered_only_under_gway_root(gateway):
    assert gateway.ops.resolve("env") is not None
    assert gateway.ops.resolve("envs") is not None
    assert "env" not in gateway.__dict__
    assert "envs" not in gateway.__dict__


def test_builtin_toml_default_operation_parses_text(gateway):
    assert gateway.ops.resolve("toml") is None

    result = gateway("toml", 'name = "gway"\n[tool]\nenabled = true')

    assert result == {"name": "gway", "tool": {"enabled": True}}
    assert gateway.ops.resolve("toml") is not None


def test_builtin_toml_loads_subject_parses_text(gateway):
    assert gateway("toml loads", "answer = 42") == {"answer": 42}


def test_builtin_toml_load_subject_reads_path(gateway, tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('site = "MTY"\n', encoding="utf-8")

    assert gateway("toml load", str(path)) == {"site": "MTY"}


def test_builtin_toml_routes_to_version_backend():
    import sys

    import gway.toml as gway_toml

    expected = "tomllib" if sys.version_info >= (3, 11) else "tomli"
    assert gway_toml._backend().__name__ == expected


def test_builtin_path_constructs_semantic_path(gateway, tmp_path):
    result = gateway("path", str(tmp_path))

    assert result == Path(tmp_path)
    assert gateway.results["path"] == result
    assert gateway.ops["path"]["path"] is gateway.ops.resolve("path")


def test_builtin_path_methods_become_semantic_operations(gateway, tmp_path):
    first = tmp_path / "first.py"
    second = tmp_path / "second.txt"
    first.write_text("print('ok')\n", encoding="utf-8")
    second.write_text("ignore\n", encoding="utf-8")

    gateway("path", str(tmp_path))
    matches = list(gateway("glob path", "*.py"))

    assert matches == [first]
    assert gateway.ops.resolve("path.glob") is not None
    assert gateway.ops["glob"]["path"] is gateway.ops.resolve("glob path")


def test_cli_invokes_path_builtin_without_internal_gway_prefix(
    monkeypatch, capsys, tmp_path
):
    monkeypatch.setattr(sys, "argv", ["gway", "path", str(tmp_path)])

    assert cli_main() == 0
    assert capsys.readouterr().out.strip() == str(tmp_path)


def test_builtin_path_pipeline_infers_glob_from_subject_and_sigils(gateway, tmp_path):
    first = tmp_path / "first.py"
    second = tmp_path / "second.txt"
    first.write_text("print('ok')\n", encoding="utf-8")
    second.write_text("ignore\n", encoding="utf-8")
    gateway.context["path"] = str(tmp_path)
    gateway.context["pattern"] = "*.py"

    matches = list(gateway("path [path] - glob [pattern]"))

    assert matches == [first]
    assert gateway.ops.resolve("path.glob") is not None
    assert gateway.ops["glob"]["path"] is gateway.ops.resolve("path.glob")


def test_clear_builtin_clears_all_accumulated_context(gateway):
    gateway.context.update({"site": "MTY", "charger": "A"})

    assert gateway("clear") is None
    assert gateway.context == {}


def test_clear_builtin_can_remove_only_named_context_flags(gateway):
    gateway.context.update({"site": "MTY", "charger": "A", "keep": 1})

    assert gateway("clear --site --charger") is None
    assert gateway.context == {"keep": 1}


def test_clear_builtin_does_not_remove_published_result_history(gateway):
    def get_site():
        return "MTY"

    gateway.get_site = gateway.wrap("get_site", get_site)
    gateway("get_site")
    gateway.context["temporary"] = True

    gateway("clear")

    assert gateway.context == {}
    assert gateway.results["site"] == "MTY"


def test_pipe_without_flags_returns_detached_context_snapshot(gateway):
    gateway.context.clear()
    gateway.context.update({"site": "MTY", "role": "Watchtower"})

    result = gateway("pipe")

    assert result == {"site": "MTY", "role": "Watchtower"}
    assert result is not gateway.context
    result["site"] = "GDL"
    assert gateway.context["site"] == "MTY"


def test_pipe_explicit_flags_returns_result_without_publishing_context(gateway):
    gateway.context.clear()
    result = gateway("pipe --site MTY --enabled")

    assert result == {"site": "MTY", "enabled": True}
    assert gateway.context == {}


def test_pipe_bare_flag_reuses_existing_context_value(gateway):
    gateway.context.clear()
    gateway.context.update({"site": "MTY", "enabled": False})

    assert gateway("pipe --site") == {"site": "MTY"}
    assert gateway("pipe --enabled") == {"enabled": False}
    assert gateway.context == {"site": "MTY", "enabled": False}


def test_pipe_bare_unknown_flag_defaults_to_true(gateway):
    gateway.context.clear()

    assert gateway("pipe --enabled") == {"enabled": True}
    assert gateway.context == {}


def test_pipe_explicit_value_overrides_existing_context(gateway):
    gateway.context.clear()
    gateway.context["site"] = "MTY"

    assert gateway("pipe --site GDL") == {"site": "GDL"}
    assert gateway.context["site"] == "MTY"


def test_pipe_result_can_feed_next_operation_without_context_leak(gateway):
    gateway.context.clear()

    def inspect(values):
        return values["site"]

    gateway.inspect = gateway.wrap("inspect", inspect)

    assert gateway("pipe --site MTY - inspect") == "MTY"
    assert "site" not in gateway.context


def test_default_publishes_flags_into_context_without_result(gateway):
    gateway.context.clear()
    history_size = len(gateway.results.history)

    gateway("default --site MTY --enabled")

    assert gateway.context == {"site": "MTY", "enabled": True}
    assert len(gateway.results.history) == history_size


def test_default_overrides_existing_context_values(gateway):
    gateway.context.clear()
    gateway.context.update({"site": "MTY", "keep": 1})

    gateway("default --site GDL")

    assert gateway.context == {"site": "GDL", "keep": 1}


def test_default_with_no_flags_is_context_noop(gateway):
    gateway.context.clear()
    gateway.context["site"] = "MTY"
    history_size = len(gateway.results.history)

    gateway("default")

    assert gateway.context == {"site": "MTY"}
    assert len(gateway.results.history) == history_size



def test_observational_builtins_support_non_mutating_execution(
    gateway,
    monkeypatch,
):
    monkeypatch.setenv("GWAY_QUERY_ENV", "visible")
    gateway.context.clear()
    gateway.context["site"] = "MTY"

    assert gateway.execute("env GWAY_QUERY_ENV", mutate=False) == "visible"
    assert gateway.execute("envs", mutate=False)["GWAY_QUERY_ENV"] == "visible"
    assert gateway.execute("pipe --site", mutate=False) == {"site": "MTY"}

    for name in ("env", "envs", "pipe"):
        assert gateway.ops.resolve(name).mutates is False



def test_toml_operations_support_non_mutating_execution(gateway, tmp_path):
    path = tmp_path / "query.toml"
    path.write_text('site = "MTY"\n', encoding="utf-8")

    assert gateway.execute("toml", 'answer = 42', mutate=False) == {"answer": 42}
    assert gateway.execute("toml loads", 'answer = 42', mutate=False) == {"answer": 42}
    assert gateway.execute("toml load", str(path), mutate=False) == {"site": "MTY"}

    family = gateway.ops["toml"]
    for name in (None, "loads", "load"):
        operation = gateway.ops.resolve("toml") if name is None else family[name]
        assert operation.mutates is False


def test_builtin_version_reports_installed_distribution(monkeypatch):
    monkeypatch.setattr("gway.builtin.package_version", lambda name: "9.8.7")

    from gway.gateway import Gateway

    gw = Gateway()
    assert gw.version() == "9.8.7"
