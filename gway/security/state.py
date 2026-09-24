"""Versioned SQLite-backed security state."""

from pathlib import Path
import sqlite3


_SCHEMA_VERSION = 5


class SecurityState:
    """Persistent store for reusable GWAY security policy."""

    def __init__(self, path):
        self.path = Path(path).expanduser().resolve()

    def connect(self, *, readonly=False):
        if readonly:
            if not self.path.is_file():
                raise FileNotFoundError(self.path)
            connection = sqlite3.connect(
                self.path.as_uri() + "?mode=ro",
                uri=True,
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version > _SCHEMA_VERSION:
                connection.close()
                raise RuntimeError(
                    "Security state schema is newer than this GWAY version: "
                    f"{version} > {_SCHEMA_VERSION}"
                )
            if version < _SCHEMA_VERSION:
                connection.close()
                raise RuntimeError(
                    "Security state requires writable schema migration before "
                    f"read-only access: {version} < {_SCHEMA_VERSION}"
                )
            return connection

        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        self._ensure_schema(connection)
        return connection

    @staticmethod
    def _ensure_schema(connection):
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version > _SCHEMA_VERSION:
            raise RuntimeError(
                "Security state schema is newer than this GWAY version: "
                f"{version} > {_SCHEMA_VERSION}"
            )

        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS scopes (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE
            );

            CREATE TABLE IF NOT EXISTS scope_operations (
                scope_id INTEGER NOT NULL,
                operation TEXT NOT NULL,
                UNIQUE(scope_id, operation),
                FOREIGN KEY(scope_id) REFERENCES scopes(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS scope_environment (
                scope_id INTEGER NOT NULL,
                variable_name TEXT NOT NULL,
                UNIQUE(scope_id, variable_name),
                FOREIGN KEY(scope_id) REFERENCES scopes(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS tokens (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                public_id TEXT NOT NULL UNIQUE,
                token_hash TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                expires_at TEXT,
                disabled INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS token_scopes (
                token_id INTEGER NOT NULL,
                scope_id INTEGER NOT NULL,
                UNIQUE(token_id, scope_id),
                FOREIGN KEY(token_id) REFERENCES tokens(id) ON DELETE CASCADE,
                FOREIGN KEY(scope_id) REFERENCES scopes(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS oauth_clients (
                id INTEGER PRIMARY KEY,
                client_id TEXT NOT NULL UNIQUE,
                metadata_url TEXT,
                redirect_uris TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                disabled INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS oauth_links (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                token_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                revoked_at TEXT,
                FOREIGN KEY(token_id) REFERENCES tokens(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS oauth_grants (
                id INTEGER PRIMARY KEY,
                link_id INTEGER NOT NULL,
                client_id TEXT NOT NULL,
                resource TEXT,
                created_at TEXT NOT NULL,
                revoked_at TEXT,
                FOREIGN KEY(link_id) REFERENCES oauth_links(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS oauth_grant_scopes (
                grant_id INTEGER NOT NULL,
                scope_id INTEGER NOT NULL,
                UNIQUE(grant_id, scope_id),
                FOREIGN KEY(grant_id) REFERENCES oauth_grants(id) ON DELETE CASCADE,
                FOREIGN KEY(scope_id) REFERENCES scopes(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS oauth_authorization_codes (
                id INTEGER PRIMARY KEY,
                grant_id INTEGER NOT NULL,
                code_hash TEXT NOT NULL UNIQUE,
                redirect_uri TEXT NOT NULL,
                code_challenge TEXT NOT NULL,
                code_challenge_method TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                consumed_at TEXT,
                FOREIGN KEY(grant_id) REFERENCES oauth_grants(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS oauth_access_tokens (
                id INTEGER PRIMARY KEY,
                grant_id INTEGER NOT NULL,
                public_id TEXT NOT NULL UNIQUE,
                token_hash TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                revoked_at TEXT,
                FOREIGN KEY(grant_id) REFERENCES oauth_grants(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS oauth_refresh_tokens (
                id INTEGER PRIMARY KEY,
                grant_id INTEGER NOT NULL,
                public_id TEXT NOT NULL UNIQUE,
                token_hash TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                revoked_at TEXT,
                rotated_at TEXT,
                FOREIGN KEY(grant_id) REFERENCES oauth_grants(id) ON DELETE CASCADE
            );
            """
        )
        if version < 3:
            columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(tokens)")
            }
            if "expires_at" not in columns:
                connection.execute("ALTER TABLE tokens ADD COLUMN expires_at TEXT")
        if version < 5:
            columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(oauth_grants)")
            }
            if "resource" not in columns:
                connection.execute("ALTER TABLE oauth_grants ADD COLUMN resource TEXT")
        if version < _SCHEMA_VERSION:
            connection.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
