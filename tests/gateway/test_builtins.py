from gway.console import process


def test_builtin_env_is_ingested_under_gway_root(gateway, monkeypatch):
    monkeypatch.setenv("GWAY_TEST_ENV", "present")

    assert gateway("gway env GWAY_TEST_ENV") == "present"
    assert gateway.ops.resolve("gway.env") is not None


def test_builtin_env_supports_default(gateway):
    assert gateway("gway env GWAY_MISSING_ENV fallback") == "fallback"


def test_builtin_env_returns_none_without_default(gateway, monkeypatch):
    monkeypatch.delenv("GWAY_MISSING_ENV", raising=False)

    assert gateway("gway env GWAY_MISSING_ENV") is None


def test_builtin_env_accepts_native_python_argument(gateway, monkeypatch):
    monkeypatch.setenv("GWAY_NATIVE_ENV", "native")

    assert gateway("gway env", "GWAY_NATIVE_ENV") == "native"


def test_builtin_env_preserves_empty_environment_value(gateway, monkeypatch):
    monkeypatch.setenv("GWAY_EMPTY_ENV", "")

    assert gateway("gway env GWAY_EMPTY_ENV fallback") == ""


def test_builtin_env_reads_current_environment_on_each_call(gateway, monkeypatch):
    monkeypatch.setenv("GWAY_DYNAMIC_ENV", "first")
    assert gateway("gway env GWAY_DYNAMIC_ENV") == "first"

    monkeypatch.setenv("GWAY_DYNAMIC_ENV", "second")
    assert gateway("gway env GWAY_DYNAMIC_ENV") == "second"


def test_builtin_envs_returns_environment_snapshot(gateway, monkeypatch):
    monkeypatch.setenv("GWAY_TEST_ENVS", "yes")

    result = gateway("gway envs")

    assert result["GWAY_TEST_ENVS"] == "yes"
    assert result is not __import__("os").environ


def test_builtin_envs_snapshot_is_not_live(gateway, monkeypatch):
    monkeypatch.setenv("GWAY_SNAPSHOT_ENV", "before")
    snapshot = gateway("gway envs")

    monkeypatch.setenv("GWAY_SNAPSHOT_ENV", "after")

    assert snapshot["GWAY_SNAPSHOT_ENV"] == "before"
    assert gateway("gway envs")["GWAY_SNAPSHOT_ENV"] == "after"


def test_builtin_env_result_is_published(gateway, monkeypatch):
    monkeypatch.setenv("GWAY_PUBLISHED_ENV", "published")

    result = gateway("gway env GWAY_PUBLISHED_ENV")

    assert result == "published"
    assert gateway.last == "published"
    assert gateway.results["gway"] == "published"


def test_builtin_envs_result_is_published_without_flattening(gateway, monkeypatch):
    monkeypatch.setenv("GWAY_PUBLISHED_ENVS", "yes")

    result = gateway("gway envs")

    assert gateway.last is result
    assert gateway.results["gway"] is result


def test_builtin_env_works_through_recipe_process(gateway, monkeypatch):
    monkeypatch.setenv("GWAY_RECIPE_ENV", "recipe")

    results, last = process(
        [["gway", "env", "GWAY_RECIPE_ENV"]],
        gw_instance=gateway,
    )

    assert results == ["recipe"]
    assert last == "recipe"


def test_builtin_envs_can_feed_next_pipeline_stage(gateway, monkeypatch):
    monkeypatch.setenv("GWAY_PIPELINE_ENV", "pipeline")

    def read_value(values, key):
        return values[key]

    gateway.read_value = gateway.wrap("read_value", read_value)

    assert gateway("gway envs - read_value GWAY_PIPELINE_ENV") == "pipeline"


def test_builtin_env_works_as_manual_chain_head(gateway, monkeypatch):
    monkeypatch.setenv("GWAY_CHAIN_ENV", "chain")

    def surround(value, prefix, suffix):
        return f"{prefix}{value}{suffix}"

    gateway.surround = gateway.wrap("surround_value", surround)

    with gateway.chain("gway env GWAY_CHAIN_ENV") as __:
        assert __("surround pre post") == "prechainpost"


def test_builtins_are_not_exposed_as_gateway_attributes(gateway):
    assert "env" not in gateway.__dict__
    assert "envs" not in gateway.__dict__


def test_builtin_module_only_registers_public_builtin_operations(gateway):
    names = {
        name
        for name in gateway.ops._registry.records
        if name.startswith("gway.")
    }

    assert names == {"gway.env", "gway.envs"}
