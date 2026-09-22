import pytest

from gway.authorization import AuthorizationError


def test_authorized_execution_allows_canonical_operation(gateway):
    gateway.read = gateway.wrap("safe.read", lambda: "ok")

    with gateway.authorized(operations={"safe.read"}):
        assert gateway("read") == "ok"


def test_authorized_execution_denies_operation_before_invocation(gateway):
    calls = []

    def dangerous():
        calls.append("called")
        return "bad"

    gateway.dangerous = gateway.wrap("dangerous", dangerous)

    with gateway.authorized(operations=set()):
        with pytest.raises(AuthorizationError, match="dangerous"):
            gateway("dangerous")

    assert calls == []


def test_multi_stage_execution_stops_at_first_denied_operation(gateway):
    calls = []

    gateway.first = gateway.wrap("first", lambda: "value")

    def second(value):
        calls.append(value)
        return value

    gateway.second = gateway.wrap("second", second)

    with gateway.authorized(operations={"first"}):
        with pytest.raises(AuthorizationError, match="second"):
            gateway("first - second")

    assert calls == []


def test_alias_authorization_uses_canonical_identity(gateway):
    wrapped = gateway.wrap("safe.read", lambda: "ok")
    gateway.ops.register_alias("shortcut", wrapped)

    with gateway.authorized(operations={"safe.read"}):
        assert gateway("shortcut") == "ok"

    with gateway.authorized(operations={"shortcut"}):
        with pytest.raises(AuthorizationError, match="safe.read"):
            gateway("shortcut")


def test_authorization_context_restores_after_failure(gateway):
    gateway.allowed = gateway.wrap("allowed", lambda: "ok")
    gateway.denied = gateway.wrap("denied", lambda: "no")

    with pytest.raises(AuthorizationError):
        with gateway.authorized(operations={"allowed"}):
            gateway("denied")

    assert gateway.authorization is None
    assert gateway("denied") == "no"


def test_environment_is_unavailable_when_scope_omits_environment(
    gateway, monkeypatch
):
    monkeypatch.setenv("GWAY_SECRET_TEST", "secret")
    gateway.echo = gateway.wrap("echo_value", lambda value: value)

    with gateway.authorized(operations={"echo_value", "env"}):
        with pytest.raises(
            AuthorizationError,
            match="Environment access is not authorized",
        ):
            gateway("echo [GWAY_SECRET_TEST]")


def test_environment_sigil_reads_through_authorized_env_operation(
    gateway, monkeypatch
):
    monkeypatch.setenv("GWAY_VISIBLE_TEST", "visible")
    gateway.echo = gateway.wrap("echo_value", lambda value: value)

    with gateway.authorized(
        operations={"echo_value", "env"},
        environment={"GWAY_VISIBLE_TEST"},
    ):
        assert gateway("echo [GWAY_VISIBLE_TEST]") == "visible"


def test_environment_sigil_requires_env_operation_authorization(
    gateway, monkeypatch
):
    monkeypatch.setenv("GWAY_VISIBLE_TEST", "visible")
    gateway.echo = gateway.wrap("echo_value", lambda value: value)

    with gateway.authorized(
        operations={"echo_value"},
        environment={"GWAY_VISIBLE_TEST"},
    ):
        with pytest.raises(AuthorizationError, match="Operation is not authorized: env"):
            gateway("echo [GWAY_VISIBLE_TEST]")


def test_envs_returns_only_granted_environment_names(gateway, monkeypatch):
    monkeypatch.setenv("GWAY_VISIBLE_A", "a")
    monkeypatch.setenv("GWAY_VISIBLE_B", "b")
    monkeypatch.setenv("GWAY_HIDDEN", "hidden")

    with gateway.authorized(
        operations={"envs"},
        environment={"GWAY_VISIBLE_A", "GWAY_VISIBLE_B"},
    ):
        assert gateway("envs") == {
            "GWAY_VISIBLE_A": "a",
            "GWAY_VISIBLE_B": "b",
        }
        assert gateway.last == {
            "GWAY_VISIBLE_A": "a",
            "GWAY_VISIBLE_B": "b",
        }


def test_envs_allows_full_environment_with_dunder_all(gateway, monkeypatch):
    monkeypatch.setenv("GWAY_ALL_TEST", "visible")

    with gateway.authorized(
        operations={"envs"},
        environment={"__all__"},
    ):
        assert gateway("envs")["GWAY_ALL_TEST"] == "visible"


def test_direct_recipe_path_is_denied_under_external_authority(
    gateway, recipe_factory
):
    gateway.internal = gateway.wrap("internal", lambda: "ok")
    recipe = recipe_factory(name="private", body="internal\n")

    with gateway.authorized(operations={"internal"}):
        with pytest.raises(AuthorizationError, match="Direct recipe paths"):
            gateway(recipe)


def test_authorized_ingested_recipe_encapsulates_internal_operations(
    gateway, recipe_factory, tmp_path
):
    gateway.internal = gateway.wrap("internal", lambda: "ok")
    root = tmp_path / "recipes"
    recipe_factory(name="deploy", body="internal\n", root=root)
    gateway.ingest(root)

    with gateway.authorized(operations={"recipes.deploy"}):
        assert gateway("recipes deploy") == "ok"

    with gateway.authorized(operations={"recipes.deploy"}):
        with pytest.raises(AuthorizationError, match="internal"):
            gateway("internal")
