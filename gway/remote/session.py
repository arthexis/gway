"""Short-lived server-side browser sessions for remote authorization."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import secrets


@dataclass
class RemoteSession:
    """Ephemeral browser state; no bearer credential is ever stored here."""

    id: str
    csrf: str
    expires_at: datetime
    link_name: str | None = None
    pending_client_id: str | None = None
    pending_scopes: frozenset[str] = field(default_factory=frozenset)
    approved_grant_id: int | None = None


class RemoteSessionStore:
    """In-memory session store suitable for one remote-auth service instance."""

    def __init__(self, *, lifetime_seconds=1800):
        lifetime_seconds = int(lifetime_seconds)
        if lifetime_seconds <= 0:
            raise ValueError("remote session lifetime must be positive")
        self.lifetime = timedelta(seconds=lifetime_seconds)
        self._sessions = {}

    @staticmethod
    def _now():
        return datetime.now(timezone.utc)

    def create(self):
        session = RemoteSession(
            id=secrets.token_urlsafe(32),
            csrf=secrets.token_urlsafe(32),
            expires_at=self._now() + self.lifetime,
        )
        self._sessions[session.id] = session
        return session

    def get(self, session_id):
        if not session_id:
            return None
        session = self._sessions.get(str(session_id))
        if session is None:
            return None
        if session.expires_at <= self._now():
            self._sessions.pop(session.id, None)
            return None
        return session

    def require(self, session_id):
        session = self.get(session_id)
        if session is None:
            raise LookupError("Remote browser session is missing or expired")
        return session

    def rotate_csrf(self, session):
        session.csrf = secrets.token_urlsafe(32)
        return session.csrf

    def destroy(self, session_id):
        return self._sessions.pop(str(session_id), None) is not None
