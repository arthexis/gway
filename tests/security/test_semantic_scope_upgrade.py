import hashlib
import sqlite3

from gway.security.oauth import OAuthRegistry
from gway.security.state import SecurityState
from gway.security.tokens import TokenRegistry


def _legacy_v7_database(path):
    bearer = "gwt_legacypublic_legacysecret"
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE scopes (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                owner TEXT
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
            CREATE TABLE tokens (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                public_id TEXT NOT NULL UNIQUE,
                token_hash TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                expires_at TEXT,
                disabled INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE token_scopes (
                token_id INTEGER NOT NULL,
                scope_id INTEGER NOT NULL,
                UNIQUE(token_id, scope_id),
                FOREIGN KEY(token_id) REFERENCES tokens(id) ON DELETE CASCADE,
                FOREIGN KEY(scope_id) REFERENCES scopes(id) ON DELETE CASCADE
            );
            CREATE TABLE oauth_links (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                token_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                revoked_at TEXT,
                FOREIGN KEY(token_id) REFERENCES tokens(id) ON DELETE CASCADE
            );
            CREATE TABLE oauth_grants (
                id INTEGER PRIMARY KEY,
                link_id INTEGER NOT NULL,
                client_id TEXT NOT NULL,
                resource TEXT,
                created_at TEXT NOT NULL,
                revoked_at TEXT,
                FOREIGN KEY(link_id) REFERENCES oauth_links(id) ON DELETE CASCADE
            );
            CREATE TABLE oauth_grant_scopes (
                grant_id INTEGER NOT NULL,
                scope_id INTEGER NOT NULL,
                UNIQUE(grant_id, scope_id),
                FOREIGN KEY(grant_id) REFERENCES oauth_grants(id) ON DELETE CASCADE,
                FOREIGN KEY(scope_id) REFERENCES scopes(id) ON DELETE CASCADE
            );
            """
        )
        connection.execute("INSERT INTO scopes (id, name, owner) VALUES (1, 'legacy-read', NULL)")
        connection.execute("INSERT INTO scopes (id, name, owner) VALUES (2, 'full-access', NULL)")
        connection.execute(
            "INSERT INTO scope_operations (scope_id, operation) VALUES (1, 'log.read')"
        )
        connection.execute(
            "INSERT INTO scope_operations (scope_id, operation) VALUES (2, '__all__')"
        )
        connection.execute(
            "INSERT INTO scope_environment (scope_id, variable_name) VALUES (2, '__all__')"
        )
        connection.execute(
            """
            INSERT INTO tokens (
                id, name, public_id, token_hash, created_at, expires_at, disabled
            ) VALUES (1, 'legacy-token', 'legacypublic', ?, '2026-01-01T00:00:00+00:00', NULL, 0)
            """,
            (hashlib.sha256(bearer.encode("utf-8")).hexdigest(),),
        )
        connection.execute("INSERT INTO token_scopes (token_id, scope_id) VALUES (1, 1)")
        connection.execute("INSERT INTO token_scopes (token_id, scope_id) VALUES (1, 2)")
        connection.execute(
            "INSERT INTO oauth_links (id, name, token_id, created_at, revoked_at) "
            "VALUES (1, 'legacy-link', 1, '2026-01-01T00:00:00+00:00', NULL)"
        )
        connection.execute(
            """
            INSERT INTO oauth_grants (
                id, link_id, client_id, resource, created_at, revoked_at
            ) VALUES (1, 1, 'legacy-client', NULL, '2026-01-01T00:00:00+00:00', NULL)
            """
        )
        connection.execute("INSERT INTO oauth_grant_scopes (grant_id, scope_id) VALUES (1, 1)")
        connection.execute("PRAGMA user_version = 7")
    return bearer


def test_v7_upgrade_preserves_exact_token_and_oauth_authority(tmp_path):
    path = tmp_path / "state.sqlite"
    bearer = _legacy_v7_database(path)

    # Production startup performs one writable security-state open before
    # credential authentication switches to the read-only path.
    with SecurityState(path).connect():
        pass

    authenticated = TokenRegistry(path).authenticate(bearer)
    grant = OAuthRegistry(path).get_grant(1)

    assert authenticated.token.scopes == frozenset({"legacy-read", "full-access"})
    assert authenticated.token.union_scopes == frozenset()
    assert authenticated.authority.operations == frozenset({"__all__", "log.read"})
    assert authenticated.authority.environment == frozenset({"__all__"})
    assert grant.scopes == frozenset({"legacy-read"})
    assert grant.union_scopes == frozenset()

    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 9
        assert connection.execute("SELECT COUNT(*) FROM scope_semantic_terms").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM token_union_scopes").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM oauth_grant_union_scopes").fetchone()[0] == 0


def test_upgrade_is_idempotent_and_does_not_reinterpret_legacy_scope_names(tmp_path):
    path = tmp_path / "state.sqlite"
    _legacy_v7_database(path)

    with SecurityState(path).connect():
        pass
    with SecurityState(path).connect():
        pass

    token = TokenRegistry(path).require("legacy-token")
    assert token.scopes == frozenset({"legacy-read", "full-access"})
    assert token.union_scopes == frozenset()

    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 9
        assert connection.execute("SELECT COUNT(*) FROM scope_semantic_terms").fetchone()[0] == 0


def test_readonly_access_requires_migration_before_using_legacy_state(tmp_path):
    path = tmp_path / "state.sqlite"
    _legacy_v7_database(path)

    try:
        SecurityState(path).connect(readonly=True)
    except RuntimeError as exc:
        assert "requires writable schema migration" in str(exc)
    else:
        raise AssertionError("legacy state unexpectedly opened read-only without migration")


def test_failed_upgrade_never_marks_schema_current(tmp_path):
    path = tmp_path / "state.sqlite"
    _legacy_v7_database(path)

    # A view occupying a schema-v9 table name forces CREATE TABLE to fail.
    # Unlike a malformed pre-existing table, SQLite does not treat this as a
    # successful CREATE TABLE IF NOT EXISTS no-op.
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE VIEW scope_semantic_terms AS SELECT 1 AS broken")

    try:
        SecurityState(path).connect()
    except sqlite3.Error:
        pass
    else:
        raise AssertionError("corrupt migration fixture unexpectedly upgraded")

    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 7
