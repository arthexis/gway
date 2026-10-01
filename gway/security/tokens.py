"""Opaque security credentials bound to curated named scopes."""

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import secrets

from ..cache import default_root
from .scopes import EffectiveScope, ScopeRegistry
from .state import SecurityState
from .usage import CredentialUsage


class AuthenticationError(PermissionError):
    """Raised when an opaque bearer credential is invalid."""

    def __init__(self):
        super().__init__("Invalid bearer token")


@dataclass(frozen=True)
class Token:
    """Safe persisted token metadata. The bearer secret is never stored here."""

    name: str
    public_id: str
    scopes: frozenset[str]
    disabled: bool
    created_at: str
    expires_at: str | None = None
    last_used_at: str | None = None


@dataclass(frozen=True)
class IssuedToken:
    token: Token
    bearer: str


@dataclass(frozen=True)
class AuthenticatedToken:
    token: Token
    authority: EffectiveScope


class TokenRegistry:
    """Persistence, verification, and scope binding for opaque bearer tokens."""

    def __init__(self, path=None):
        path = default_root() / "security" / "state.sqlite" if path is None else path
        self.state = SecurityState(path)
        self.scopes = ScopeRegistry(path)
        self.usage = CredentialUsage(path)

    @property
    def path(self):
        return self.state.path

    @staticmethod
    def _name(value):
        value = str(value).strip()
        if not value:
            raise ValueError("token name must be a non-empty string")
        return value

    @staticmethod
    def _hash(bearer):
        return hashlib.sha256(str(bearer).encode("utf-8")).hexdigest()

    @staticmethod
    def _bearer(public_id, secret):
        return f"gwt_{public_id}_{secret}"

    @staticmethod
    def _public_id(bearer):
        try:
            prefix, public_id, secret = str(bearer).split("_", 2)
        except ValueError:
            raise AuthenticationError() from None
        if prefix != "gwt" or not public_id or not secret:
            raise AuthenticationError()
        return public_id

    @staticmethod
    def _scope_names(connection, token_id):
        return frozenset(
            row["name"]
            for row in connection.execute(
                """
                SELECT scopes.name
                FROM token_scopes
                JOIN scopes ON scopes.id = token_scopes.scope_id
                WHERE token_scopes.token_id = ?
                ORDER BY scopes.name
                """,
                (token_id,),
            )
        )

    @classmethod
    def _from_row(cls, connection, row):
        if row is None:
            return None
        return Token(
            name=row["name"],
            public_id=row["public_id"],
            scopes=cls._scope_names(connection, row["id"]),
            disabled=bool(row["disabled"]),
            created_at=row["created_at"],
            expires_at=row["expires_at"],
        )

    def _with_usage(self, token):
        if token is None:
            return None
        return Token(
            name=token.name,
            public_id=token.public_id,
            scopes=token.scopes,
            disabled=token.disabled,
            created_at=token.created_at,
            expires_at=token.expires_at,
            last_used_at=self.usage.get("token", token.public_id),
        )

    def get(self, name, *, readonly=False):
        if not self.path.is_file():
            return None
        name = self._name(name)
        with self.state.connect(readonly=readonly) as connection:
            row = connection.execute(
                "SELECT id, name, public_id, disabled, created_at, expires_at FROM tokens WHERE name = ?",
                (name,),
            ).fetchone()
            token = self._from_row(connection, row)
        return self._with_usage(token)

    def require(self, name, *, readonly=False):
        token = self.get(name, readonly=readonly)
        if token is None:
            raise LookupError(f"Unknown security token: {name}")
        return token

    def all(self, *, readonly=False):
        if not self.path.is_file():
            return []
        with self.state.connect(readonly=readonly) as connection:
            rows = connection.execute(
                "SELECT id, name, public_id, disabled, created_at, expires_at FROM tokens ORDER BY name"
            ).fetchall()
            tokens = [self._from_row(connection, row) for row in rows]
        return [self._with_usage(token) for token in tokens]

    @staticmethod
    def _expiry(value):
        if value is None:
            return None
        if isinstance(value, datetime):
            expires = value
        else:
            try:
                expires = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("token expiry must be a timezone-aware ISO-8601 timestamp") from exc
        if expires.tzinfo is None or expires.utcoffset() is None:
            raise ValueError("token expiry must be a timezone-aware ISO-8601 timestamp")
        return expires.astimezone(timezone.utc).isoformat()

    def create(self, name, *, scopes=(), expires_at=None):
        name = self._name(name)
        scope_names = self._validate_scope_names(scopes)
        expires_at = self._expiry(expires_at)
        public_id = secrets.token_hex(8)
        secret = secrets.token_urlsafe(32)
        bearer = self._bearer(public_id, secret)
        created_at = datetime.now(timezone.utc).isoformat()
        with self.state.connect() as connection:
            try:
                cursor = connection.execute(
                    "INSERT INTO tokens (name, public_id, token_hash, created_at, expires_at, disabled) VALUES (?, ?, ?, ?, ?, 0)",
                    (name, public_id, self._hash(bearer), created_at, expires_at),
                )
            except Exception:
                if connection.execute("SELECT 1 FROM tokens WHERE name = ?", (name,)).fetchone():
                    raise ValueError(f"Security token already exists: {name}") from None
                raise
            self._replace_scope_bindings(connection, cursor.lastrowid, scope_names)
        return IssuedToken(self.require(name), bearer)

    def rename(self, name, new_name):
        """Rename a token while preserving its stable identity and all bindings."""
        name = self._name(name)
        new_name = self._name(new_name)
        with self.state.connect() as connection:
            row = connection.execute(
                "SELECT id FROM tokens WHERE name = ?",
                (name,),
            ).fetchone()
            if row is None:
                raise LookupError(f"Unknown security token: {name}")
            if connection.execute(
                "SELECT 1 FROM tokens WHERE name = ?",
                (new_name,),
            ).fetchone():
                raise ValueError(f"Security token already exists: {new_name}")
            connection.execute(
                "UPDATE tokens SET name = ? WHERE id = ?",
                (new_name, row["id"]),
            )
        return self.require(new_name)

    def remove(self, name):
        if not self.path.is_file():
            return False
        name = self._name(name)
        with self.state.connect() as connection:
            cursor = connection.execute("DELETE FROM tokens WHERE name = ?", (name,))
        return bool(cursor.rowcount)

    def clear(self):
        if not self.path.is_file():
            return 0
        with self.state.connect() as connection:
            cursor = connection.execute("DELETE FROM tokens")
        return int(cursor.rowcount)

    def disable(self, name):
        return self._set_disabled(name, True)

    def enable(self, name):
        return self._set_disabled(name, False)

    def _set_disabled(self, name, disabled):
        name = self._name(name)
        with self.state.connect() as connection:
            cursor = connection.execute(
                "UPDATE tokens SET disabled = ? WHERE name = ?",
                (int(disabled), name),
            )
            if not cursor.rowcount:
                raise LookupError(f"Unknown security token: {name}")
        return self.require(name)

    def _validate_scope_names(self, names):
        result = frozenset(str(name).strip() for name in names)
        if "" in result:
            raise ValueError("scope names must be non-empty strings")
        for name in result:
            self.scopes.require(name)
        return result

    @staticmethod
    def _replace_scope_bindings(connection, token_id, scope_names):
        connection.execute("DELETE FROM token_scopes WHERE token_id = ?", (token_id,))
        for name in sorted(scope_names):
            row = connection.execute(
                "SELECT id FROM scopes WHERE name = ?", (name,)
            ).fetchone()
            if row is None:
                raise LookupError(f"Unknown security scope: {name}")
            connection.execute(
                "INSERT INTO token_scopes (token_id, scope_id) VALUES (?, ?)",
                (token_id, row["id"]),
            )

    def replace_scopes(self, name, scopes):
        name = self._name(name)
        scope_names = self._validate_scope_names(scopes)
        with self.state.connect() as connection:
            row = connection.execute(
                "SELECT id FROM tokens WHERE name = ?", (name,)
            ).fetchone()
            if row is None:
                raise LookupError(f"Unknown security token: {name}")
            self._replace_scope_bindings(connection, row["id"], scope_names)
        return self.require(name)

    def bind(self, name, scope):
        token = self.require(name)
        scopes = set(token.scopes)
        scopes.add(str(scope))
        return self.replace_scopes(name, scopes)

    def unbind(self, name, scope):
        token = self.require(name)
        scopes = set(token.scopes)
        scopes.discard(str(scope))
        return self.replace_scopes(name, scopes)

    def _effective_authority(self, token, *, readonly):
        return self.scopes.resolve(token.scopes, readonly=readonly)

    def authenticate(self, bearer, *, readonly=True):
        public_id = self._public_id(bearer)
        if not self.path.is_file():
            raise AuthenticationError()
        with self.state.connect(readonly=readonly) as connection:
            row = connection.execute(
                "SELECT id, name, public_id, token_hash, disabled, created_at, expires_at FROM tokens WHERE public_id = ?",
                (public_id,),
            ).fetchone()
            if row is None or bool(row["disabled"]):
                raise AuthenticationError()
            if row["expires_at"] is not None:
                expires = datetime.fromisoformat(row["expires_at"])
                if expires <= datetime.now(timezone.utc):
                    raise AuthenticationError()
            if not secrets.compare_digest(row["token_hash"], self._hash(bearer)):
                raise AuthenticationError()
            token = self._from_row(connection, row)
        authority = self._effective_authority(token, readonly=readonly)
        used_at = self.usage.touch("token", token.public_id)
        if used_at is not None:
            token = Token(
                name=token.name,
                public_id=token.public_id,
                scopes=token.scopes,
                disabled=token.disabled,
                created_at=token.created_at,
                expires_at=token.expires_at,
                last_used_at=used_at,
            )
        return AuthenticatedToken(token, authority)
