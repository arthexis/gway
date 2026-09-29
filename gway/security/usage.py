"""Best-effort credential usage telemetry kept outside authorization state."""

from datetime import datetime, timezone
from pathlib import Path
import sqlite3


class CredentialUsage:
    """Track successful credential use without changing security policy schema."""

    def __init__(self, security_path):
        path = Path(security_path).expanduser().resolve()
        self.path = path.with_name("usage.sqlite")

    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=2)
        connection.row_factory = sqlite3.Row
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS credential_usage (
                kind TEXT NOT NULL,
                public_id TEXT NOT NULL,
                last_used_at TEXT NOT NULL,
                PRIMARY KEY (kind, public_id)
            )
            """
        )
        return connection

    def touch(self, kind, public_id, *, when=None):
        """Record one successful use and return its timestamp."""
        when = when or datetime.now(timezone.utc).isoformat()
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO credential_usage (kind, public_id, last_used_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(kind, public_id)
                    DO UPDATE SET last_used_at = excluded.last_used_at
                    """,
                    (str(kind), str(public_id), when),
                )
        except (OSError, sqlite3.Error):
            # Usage is observability, not authorization state. A telemetry failure
            # must not reject an otherwise valid credential.
            return None
        return when

    def get(self, kind, public_id):
        """Return the last successful-use timestamp, if any."""
        if not self.path.is_file():
            return None
        try:
            with sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True) as connection:
                row = connection.execute(
                    """
                    SELECT last_used_at
                    FROM credential_usage
                    WHERE kind = ? AND public_id = ?
                    """,
                    (str(kind), str(public_id)),
                ).fetchone()
        except (OSError, sqlite3.Error):
            return None
        return None if row is None else row[0]

    def remove(self, kind, public_id):
        """Forget telemetry for one credential without touching policy state."""
        if not self.path.is_file():
            return False
        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    "DELETE FROM credential_usage WHERE kind = ? AND public_id = ?",
                    (str(kind), str(public_id)),
                )
        except (OSError, sqlite3.Error):
            return False
        return bool(cursor.rowcount)
