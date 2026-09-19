def test_builtin_env_is_ingested_under_gway_root(gateway, monkeypatch):
    monkeypatch.setenv("GWAY_TEST_ENV", "present")

    assert gateway("gway env GWAY_TEST_ENV") == "present"
    assert gateway.ops.resolve("gway.env") is not None


def test_builtin_env_supports_default(gateway):
    assert gateway("gway env GWAY_MISSING_ENV fallback") == "fallback"


def test_builtin_envs_returns_environment_snapshot(gateway, monkeypatch):
    monkeypatch.setenv("GWAY_TEST_ENVS", "yes")

    result = gateway("gway envs")

    assert result["GWAY_TEST_ENVS"] == "yes"
    assert result is not __import__("os").environ


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
