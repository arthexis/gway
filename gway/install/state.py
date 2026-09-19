"""SQLite-backed authoritative installation state."""

from datetime import datetime, timezone
from pathlib import Path
import sqlite3

from .model import Installation


_SCHEMA_VERSION = 1


class InstallState:
    """Persistent installation registry separate from disposable cache state."""

    def __init__(self, path):
        self.path = Path(path).expanduser().resolve()

    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        self._ensure_schema(connection)
        return connection

    @staticmethod
    def _ensure_schema(connection):
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version > _SCHEMA_VERSION:
            raise RuntimeError(
                "Installation state schema is newer than this GWAY version: "
                f"{version} > {_SCHEMA_VERSION}"
            )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS installations (
                name TEXT NOT NULL,
                scope TEXT NOT NULL,
                source TEXT NOT NULL,
                requested_ref TEXT,
                resolved_revision TEXT,
                fingerprint TEXT,
                install_path TEXT NOT NULL,
                installed_at TEXT NOT NULL,
                PRIMARY KEY (name, scope)
            )
            """
        )
        if version < _SCHEMA_VERSION:
            connection.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")

    @staticmethod
    def _from_row(row):
        if row is None:
            return None
        return Installation(
            name=row["name"],
            scope=row["scope"],
            source=row["source"],
            requested_ref=row["requested_ref"],
            resolved_revision=row["resolved_revision"],
            fingerprint=row["fingerprint"],
            install_path=Path(row["install_path"]),
            installed_at=row["installed_at"],
        )

    def get(self, name, *, scope="user"):
        """Return one installation without creating state when none exists."""
        if not self.path.is_file():
            return None
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT name, scope, source, requested_ref, resolved_revision,
                       fingerprint, install_path, installed_at
                FROM installations
                WHERE name = ? AND scope = ?
                """,
                (name, scope),
            ).fetchone()
        return self._from_row(row)

    def all(self, *, scope=None):
        """Return registered installations in stable name/scope order."""
        if not self.path.is_file():
            return []
        query = """
            SELECT name, scope, source, requested_ref, resolved_revision,
                   fingerprint, install_path, installed_at
            FROM installations
        """
        values = ()
        if scope is not None:
            query += " WHERE scope = ?"
            values = (scope,)
        query += " ORDER BY name, scope"

        with self._connect() as connection:
            rows = connection.execute(query, values).fetchall()
        return [self._from_row(row) for row in rows]

    def put(self, installation):
        """Insert or replace one authoritative installation record."""
        if not isinstance(installation, Installation):
            raise TypeError("installation state requires an Installation record")

        installed_at = installation.installed_at or datetime.now(
            timezone.utc
        ).isoformat()
        record = installation.with_installed_at(installed_at)

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO installations (
                    name, scope, source, requested_ref, resolved_revision,
                    fingerprint, install_path, installed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name, scope) DO UPDATE SET
                    source = excluded.source,
                    requested_ref = excluded.requested_ref,
                    resolved_revision = excluded.resolved_revision,
                    fingerprint = excluded.fingerprint,
                    install_path = excluded.install_path,
                    installed_at = excluded.installed_at
                """,
                (
                    record.name,
                    record.scope,
                    record.source,
                    record.requested_ref,
                    record.resolved_revision,
                    record.fingerprint,
                    str(record.install_path),
                    record.installed_at,
                ),
            )
        return record

    def remove(self, name, *, scope="user"):
        """Remove one record and report whether it existed."""
        if not self.path.is_file():
            return False
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM installations WHERE name = ? AND scope = ?",
                (name, scope),
            )
        return bool(cursor.rowcount)
