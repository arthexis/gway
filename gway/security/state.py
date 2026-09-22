"""Versioned SQLite-backed security state."""

from pathlib import Path
import sqlite3


_SCHEMA_VERSION = 2


class SecurityState:
    """Persistent store for reusable GWAY security policy."""

    def __init__(self, path):
        self.path = Path(path).expanduser().resolve()

    def connect(self):
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
                disabled INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS token_scopes (
                token_id INTEGER NOT NULL,
                scope_id INTEGER NOT NULL,
                UNIQUE(token_id, scope_id),
                FOREIGN KEY(token_id) REFERENCES tokens(id) ON DELETE CASCADE,
                FOREIGN KEY(scope_id) REFERENCES scopes(id) ON DELETE CASCADE
            );
            """
        )
        if version < _SCHEMA_VERSION:
            connection.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
