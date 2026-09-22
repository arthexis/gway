import sqlite3

import pytest

from gway.security import scope as scope_commands
from gway.security import token as token_commands
from gway.security.scopes import ScopeRegistry
from gway.security.tokens import (
    AuthenticatedToken,
    AuthenticationError,
    IssuedToken,
    Token,
    TokenRegistry,
)


def _registries(tmp_path):
    path = tmp_path / "security.sqlite"
    return ScopeRegistry(path), TokenRegistry(path)


def test_security_state_migrates_v1_scopes_to_v2_without_data_loss(tmp_path):
    path = tmp_path / "security.sqlite"
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE scopes (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE
            );
            CREATE TABLE scope_operations (
                scope_id INTEGER NOT NULL,
                operation TEXT NOT NULL,
                UNIQUE(scope_id, operation),
                FOREIGN KEY(scope_id) REFERENCES scopes(id) ON DELETE CASCADE
            );
            CREATE TABLE scope_environment (
                scope_id INTEGER NOT NULL,
                variable_name TEXT NOT NULL,
                UNIQUE(scope_id, variable_name),
                FOREIGN KEY(scope_id) REFERENCES scopes(id) ON DELETE CASCADE
            );
            INSERT INTO scopes (name) VALUES ('logs');
            INSERT INTO scope_operations (scope_id, operation)
            SELECT id, 'log.read' FROM scopes WHERE name = 'logs';
            PRAGMA user_version = 1;
            """
        )

    scopes = ScopeRegistry(path)
    tokens = TokenRegistry(path)

    assert scopes.require("logs").operations == frozenset({"log.read"})
    issued = tokens.create("reader", scopes={"logs"})
    assert issued.token.scopes == frozenset({"logs"})

    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2


def test_token_create_returns_secret_once_and_persists_only_safe_metadata(tmp_path):
    scopes, tokens = _registries(tmp_path)
    scopes.create("logs")

    issued = tokens.create("reader", scopes={"logs"})

    assert isinstance(issued, IssuedToken)
    assert issued.bearer.startswith(f"gwt_{issued.token.public_id}_")
    assert tokens.get("reader") == issued.token
    assert tokens.all() == [issued.token]
    assert not hasattr(tokens.get("reader"), "bearer")

    with sqlite3.connect(tokens.path) as connection:
        row = connection.execute(
            "SELECT token_hash, public_id FROM tokens WHERE name = 'reader'"
        ).fetchone()
        stored = "\n".join(
            value
            for dbrow in connection.iterdump()
            for value in (dbrow,)
        )
    assert row[0] != issued.bearer
    assert issued.bearer not in stored


def test_token_authentication_resolves_bound_scope_authority(tmp_path):
    scopes, tokens = _registries(tmp_path)
    scopes.replace("logs", operations={"log.read"}, environment={"LOG_LEVEL"})
    scopes.replace("status", operations={"status"}, environment={"SITE"})
    issued = tokens.create("agent", scopes={"logs", "status"})

    authenticated = tokens.authenticate(issued.bearer)

    assert isinstance(authenticated, AuthenticatedToken)
    assert authenticated.token == issued.token
    assert authenticated.authority.operations == frozenset({"log.read", "status"})
    assert authenticated.authority.environment == frozenset({"LOG_LEVEL", "SITE"})


@pytest.mark.parametrize(
    "bearer",
    [
        "not-a-token",
        "gwt_missing_wrong",
    ],
)
def test_invalid_tokens_use_one_external_error(tmp_path, bearer):
    tokens = TokenRegistry(tmp_path / "security.sqlite")

    with pytest.raises(AuthenticationError, match="Invalid bearer token"):
        tokens.authenticate(bearer)


def test_wrong_secret_and_disabled_token_are_indistinguishable(tmp_path):
    scopes, tokens = _registries(tmp_path)
    scopes.create("logs")
    issued = tokens.create("reader", scopes={"logs"})
    wrong = f"gwt_{issued.token.public_id}_wrong"

    with pytest.raises(AuthenticationError, match="Invalid bearer token"):
        tokens.authenticate(wrong)

    disabled = tokens.disable("reader")
    assert disabled.disabled is True

    with pytest.raises(AuthenticationError, match="Invalid bearer token"):
        tokens.authenticate(issued.bearer)

    enabled = tokens.enable("reader")
    assert enabled.disabled is False
    assert tokens.authenticate(issued.bearer).token.name == "reader"


def test_token_scope_replacement_removes_stale_bindings(tmp_path):
    scopes, tokens = _registries(tmp_path)
    scopes.create("one")
    scopes.create("two")
    scopes.create("three")
    tokens.create("agent", scopes={"one", "two"})

    updated = tokens.replace_scopes("agent", {"three"})

    assert updated.scopes == frozenset({"three"})


def test_failed_token_scope_replacement_preserves_previous_bindings(tmp_path):
    scopes, tokens = _registries(tmp_path)
    scopes.create("one")
    tokens.create("agent", scopes={"one"})

    with pytest.raises(LookupError, match="Unknown security scope"):
        tokens.replace_scopes("agent", {"missing"})

    assert tokens.require("agent").scopes == frozenset({"one"})


def test_bind_and_unbind_delegate_to_convergent_scope_policy(tmp_path):
    scopes, tokens = _registries(tmp_path)
    scopes.create("one")
    scopes.create("two")
    tokens.create("agent", scopes={"one"})

    assert tokens.bind("agent", "two").scopes == frozenset({"one", "two"})
    assert tokens.unbind("agent", "one").scopes == frozenset({"two"})


def test_scope_deletion_cascades_token_binding(tmp_path):
    scopes, tokens = _registries(tmp_path)
    scopes.create("logs")
    issued = tokens.create("reader", scopes={"logs"})

    assert scopes.remove("logs") is True
    assert tokens.require("reader").scopes == frozenset()
    assert tokens.authenticate(issued.bearer).authority.operations == frozenset()


def test_token_delete_cascades_bindings(tmp_path):
    scopes, tokens = _registries(tmp_path)
    scopes.create("logs")
    tokens.create("reader", scopes={"logs"})

    assert tokens.remove("reader") is True
    assert tokens.remove("reader") is False

    with sqlite3.connect(tokens.path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM token_scopes").fetchone()[0] == 0


def test_duplicate_token_name_fails(tmp_path):
    scopes, tokens = _registries(tmp_path)
    scopes.create("logs")
    tokens.create("reader", scopes={"logs"})

    with pytest.raises(ValueError, match="already exists"):
        tokens.create("reader", scopes={"logs"})


def test_security_token_gway_command_surface(gateway, tmp_path, monkeypatch):
    path = tmp_path / "security.sqlite"
    scopes = ScopeRegistry(path)
    tokens = TokenRegistry(path)
    scopes.create("logs")

    monkeypatch.setattr(scope_commands, "_registry", scopes)
    monkeypatch.setattr(token_commands, "_registry", tokens)

    bearer = gateway("security token create reader logs")
    assert bearer.startswith("gwt_")

    shown = gateway("security token show reader")
    assert isinstance(shown, Token)
    assert shown.name == "reader"
    assert shown.scopes == frozenset({"logs"})
    assert bearer not in repr(shown)

    assert gateway("security token list") == [shown]
    assert gateway("security token disable reader").disabled is True
    assert gateway("security token enable reader").disabled is False

    scopes.create("status")
    assert gateway("security token bind reader status").scopes == frozenset(
        {"logs", "status"}
    )
    assert gateway("security token unbind reader logs").scopes == frozenset({"status"})
    assert gateway("security token set reader logs").scopes == frozenset({"logs"})

    assert gateway("security token delete reader") is True
    assert gateway("security token list") == []
