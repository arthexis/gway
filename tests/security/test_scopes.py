import sqlite3

import pytest

from gway.security import scope as scope_commands
from gway.security.scopes import EffectiveScope, Scope, ScopeRegistry
from gway.security.state import SecurityState


def test_scope_reads_are_lazy_when_database_does_not_exist(tmp_path):
    path = tmp_path / "security.sqlite"
    registry = ScopeRegistry(path)

    assert registry.get("missing") is None
    assert registry.all() == []
    assert registry.remove("missing") is False
    assert not path.exists()


def test_scope_create_round_trips_and_versions_schema(tmp_path):
    path = tmp_path / "security.sqlite"
    registry = ScopeRegistry(path)

    assert registry.create("logs-read") == Scope("logs-read")
    assert registry.get("logs-read") == Scope("logs-read")

    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 5


def test_scope_replace_is_atomic_complete_definition(tmp_path):
    registry = ScopeRegistry(tmp_path / "security.sqlite")
    registry.replace(
        "logs-read",
        operations={"log.read", "log.tail"},
        environment={"GWAY_LOG_LEVEL"},
    )

    replaced = registry.replace(
        "logs-read",
        operations={"log.sources"},
        environment=(),
    )

    assert replaced == Scope(
        "logs-read",
        frozenset({"log.sources"}),
        frozenset(),
    )


def test_scope_grants_are_unique_and_stably_loaded(tmp_path):
    registry = ScopeRegistry(tmp_path / "security.sqlite")
    scope = registry.replace(
        "duplicate",
        operations=["log.read", "log.read"],
        environment=["FOO", "FOO"],
    )

    assert scope.operations == frozenset({"log.read"})
    assert scope.environment == frozenset({"FOO"})


def test_scope_dunder_all_round_trips(tmp_path):
    registry = ScopeRegistry(tmp_path / "security.sqlite")

    scope = registry.replace("admin", environment={"__all__"})

    assert scope.environment == frozenset({"__all__"})


def test_scope_remove_cascades_grants(tmp_path):
    path = tmp_path / "security.sqlite"
    registry = ScopeRegistry(path)
    registry.replace(
        "temporary",
        operations={"log.read"},
        environment={"FOO"},
    )

    assert registry.remove("temporary") is True
    assert registry.remove("temporary") is False
    assert registry.get("temporary") is None

    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM scope_operations").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM scope_environment").fetchone()[0] == 0


def test_scope_union_combines_operations_and_environment(tmp_path):
    registry = ScopeRegistry(tmp_path / "security.sqlite")
    registry.replace("logs", operations={"log.read"}, environment={"LOG_LEVEL"})
    registry.replace("status", operations={"status"}, environment={"SITE"})

    assert registry.resolve(["logs", "status"]) == EffectiveScope(
        frozenset({"log.read", "status"}),
        frozenset({"LOG_LEVEL", "SITE"}),
    )


def test_scope_union_preserves_dunder_all(tmp_path):
    registry = ScopeRegistry(tmp_path / "security.sqlite")
    registry.replace("limited", environment={"FOO"})
    registry.replace("admin", environment={"__all__"})

    assert registry.resolve(["limited", "admin"]).environment == frozenset(
        {"FOO", "__all__"}
    )


def test_missing_scope_fails_explicitly(tmp_path):
    registry = ScopeRegistry(tmp_path / "security.sqlite")

    with pytest.raises(LookupError, match="Unknown security scope"):
        registry.require("missing")

    with pytest.raises(LookupError, match="Unknown security scope"):
        registry.resolve(["missing"])


def test_duplicate_create_fails(tmp_path):
    registry = ScopeRegistry(tmp_path / "security.sqlite")
    registry.create("logs")

    with pytest.raises(ValueError, match="already exists"):
        registry.create("logs")


def test_security_state_rejects_newer_schema(tmp_path):
    path = tmp_path / "security.sqlite"
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA user_version = 99")

    registry = ScopeRegistry(path)

    with pytest.raises(RuntimeError, match="newer than this GWAY version"):
        registry.all()


def test_failed_replace_rolls_back_previous_scope(tmp_path, monkeypatch):
    registry = ScopeRegistry(tmp_path / "security.sqlite")
    original = registry.replace("logs", operations={"log.read"})

    original_connect = SecurityState.connect

    class BrokenConnection:
        def __init__(self, connection):
            self.connection = connection

        def __enter__(self):
            self.connection.__enter__()
            return self

        def __exit__(self, *args):
            return self.connection.__exit__(*args)

        def __getattr__(self, name):
            return getattr(self.connection, name)

        def executemany(self, sql, values):
            if "scope_operations" in sql:
                raise RuntimeError("boom")
            return self.connection.executemany(sql, values)

    def broken_connect(state):
        return BrokenConnection(original_connect(state))

    monkeypatch.setattr(SecurityState, "connect", broken_connect)

    with pytest.raises(RuntimeError, match="boom"):
        registry.replace("logs", operations={"log.tail"})

    monkeypatch.setattr(SecurityState, "connect", original_connect)
    assert registry.get("logs") == original



def test_security_scope_gway_command_surface(gateway, tmp_path, monkeypatch):
    registry = ScopeRegistry(tmp_path / "security.sqlite")
    monkeypatch.setattr(scope_commands, "_registry", registry)

    created = gateway("security scope create logs")
    assert created == Scope("logs")

    updated = gateway(
        "security scope set logs log.read log.tail --environment GWAY_LOG_LEVEL"
    )
    assert updated == Scope(
        "logs",
        frozenset({"log.read", "log.tail"}),
        frozenset({"GWAY_LOG_LEVEL"}),
    )

    assert gateway("security scope show logs") == updated
    assert gateway("security scope list") == [updated]
    assert gateway("security scope delete logs") is True
    assert gateway("security scope list") == []



def test_scope_toml_apply_and_export_round_trip(gateway, tmp_path, monkeypatch):
    registry = ScopeRegistry(tmp_path / "security.sqlite")
    monkeypatch.setattr(scope_commands, "_registry", registry)
    source = tmp_path / "scopes.toml"
    source.write_text(
        """
[scopes.logs-read]
operations = ["log.sources", "log.read", "log.tail", "log.search"]
environment = []

[scopes.operator]
operations = ["status"]
environment = ["SITE"]
""".lstrip(),
        encoding="utf-8",
    )

    first = gateway(f"security scope apply {source}")
    second = gateway(f"security scope apply {source}")

    assert first == second
    assert [scope.name for scope in first] == ["logs-read", "operator"]
    assert registry.require("logs-read").operations == frozenset(
        {"log.sources", "log.read", "log.tail", "log.search"}
    )
    assert registry.require("operator").environment == frozenset({"SITE"})

    exported = tmp_path / "exported.toml"
    assert gateway(f"security scope export --to {exported}") == str(exported)
    assert "[scopes.\"logs-read\"]" in exported.read_text(encoding="utf-8")

    replacement = ScopeRegistry(tmp_path / "replacement.sqlite")
    monkeypatch.setattr(scope_commands, "_registry", replacement)
    gateway(f"security scope apply {exported}")

    assert replacement.all() == registry.all()


def test_scope_toml_apply_is_transactional(tmp_path, monkeypatch):
    registry = ScopeRegistry(tmp_path / "security.sqlite")
    registry.replace("existing", operations={"old"})
    original_connect = SecurityState.connect
    calls = 0

    class BrokenConnection:
        def __init__(self, connection):
            self.connection = connection

        def __enter__(self):
            self.connection.__enter__()
            return self

        def __exit__(self, *args):
            return self.connection.__exit__(*args)

        def __getattr__(self, name):
            return getattr(self.connection, name)

        def executemany(self, sql, values):
            nonlocal calls
            if "scope_operations" in sql:
                calls += 1
                if calls == 2:
                    raise RuntimeError("second scope failed")
            return self.connection.executemany(sql, values)

    monkeypatch.setattr(
        SecurityState,
        "connect",
        lambda state: BrokenConnection(original_connect(state)),
    )

    with pytest.raises(RuntimeError, match="second scope failed"):
        registry.replace_many(
            {
                "existing": {"operations": ["new"]},
                "second": {"operations": ["other"]},
            }
        )

    monkeypatch.setattr(SecurityState, "connect", original_connect)
    assert registry.require("existing").operations == frozenset({"old"})
    assert registry.get("second") is None


def test_scope_toml_rejects_unknown_fields(tmp_path):
    registry = ScopeRegistry(tmp_path / "security.sqlite")

    with pytest.raises(ValueError, match="Unknown scope fields"):
        registry.replace_many(
            {"logs": {"operations": ["log.read"], "wildcard": ["*"]}}
        )



def test_readonly_security_state_never_migrates_schema(tmp_path):
    path = tmp_path / "security.sqlite"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE scopes (id INTEGER PRIMARY KEY, name TEXT)")
        connection.execute("PRAGMA user_version = 1")

    state = SecurityState(path)

    with pytest.raises(RuntimeError, match="requires writable schema migration"):
        state.connect(readonly=True)

    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1


def test_security_scope_reads_support_forced_non_mutation(
    gateway,
    tmp_path,
    monkeypatch,
):
    path = tmp_path / "security.sqlite"
    registry = ScopeRegistry(path)
    registry.replace("logs", operations={"log.read"})
    monkeypatch.setattr(scope_commands, "_registry", registry)
    before = path.read_bytes()

    shown = gateway.execute("security scope show logs", mutate=False)
    listed = gateway.execute("security scope list", mutate=False)
    resolved = gateway.execute("security scope resolve logs", mutate=False)

    assert shown.name == "logs"
    assert listed == [shown]
    assert resolved.operations == frozenset({"log.read"})
    assert path.read_bytes() == before

    for name in (
        "security.scope.show",
        "security.scope.list",
        "security.scope.resolve",
    ):
        operation = gateway.ops.resolve(name)
        assert operation.__gway_supports_no_mutate__ is True
        assert operation.mutates is True
