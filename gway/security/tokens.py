"""Opaque security credentials bound to exact and union scopes."""

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import secrets

from ..cache import default_root
from .scopes import EffectiveScope, ScopeRegistry
from .semantics import resolve as resolve_semantic
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
    union_scopes: frozenset[tuple[str, ...]] = frozenset()


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

    @staticmethod
    def _union_scopes(connection, token_id):
        return frozenset(
            tuple(json.loads(row["terms"]))
            for row in connection.execute(
                "SELECT terms FROM token_union_scopes WHERE token_id = ? ORDER BY terms",
                (token_id,),
            )
        )

    @staticmethod
    def _union_terms(values):
        if values is None:
            return frozenset()
        result = set()
        for value in values:
            if isinstance(value, str):
                raw = value.replace(",", " ").split()
            else:
                raw = value
            terms = tuple(sorted({str(term).strip().lower() for term in raw if str(term).strip()}))
            if not terms:
                raise ValueError("union scope requires at least one term")
            result.add(terms)
        return frozenset(result)

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
            union_scopes=cls._union_scopes(connection, row["id"]),
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
            union_scopes=token.union_scopes,
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

    def create(self, name, *, scopes=(), union_scopes=(), expires_at=None):
        name = self._name(name)
        scope_names = self._validate_scope_names(scopes)
        unions = self._union_terms(union_scopes)
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
            self._replace_union_bindings(connection, cursor.lastrowid, unions)
        return IssuedToken(self.require(name), bearer)

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
            cursor = connection.execute("UPDATE tokens SET disabled = ? WHERE name = ?", (int(disabled), name))
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
            row = connection.execute("SELECT id FROM scopes WHERE name = ?", (name,)).fetchone()
            if row is None:
                raise LookupError(f"Unknown security scope: {name}")
            connection.execute("INSERT INTO token_scopes (token_id, scope_id) VALUES (?, ?)", (token_id, row["id"]))

    @staticmethod
    def _replace_union_bindings(connection, token_id, unions):
        connection.execute("DELETE FROM token_union_scopes WHERE token_id = ?", (token_id,))
        connection.executemany(
            "INSERT INTO token_union_scopes (token_id, terms) VALUES (?, ?)",
            ((token_id, json.dumps(list(terms), separators=(",", ":"))) for terms in sorted(unions)),
        )

    def replace_scopes(self, name, scopes):
        name = self._name(name)
        scope_names = self._validate_scope_names(scopes)
        with self.state.connect() as connection:
            row = connection.execute("SELECT id FROM tokens WHERE name = ?", (name,)).fetchone()
            if row is None:
                raise LookupError(f"Unknown security token: {name}")
            self._replace_scope_bindings(connection, row["id"], scope_names)
        return self.require(name)

    def replace_union_scopes(self, name, union_scopes):
        name = self._name(name)
        unions = self._union_terms(union_scopes)
        with self.state.connect() as connection:
            row = connection.execute("SELECT id FROM tokens WHERE name = ?", (name,)).fetchone()
            if row is None:
                raise LookupError(f"Unknown security token: {name}")
            self._replace_union_bindings(connection, row["id"], unions)
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

    def bind_union(self, name, *terms):
        token = self.require(name)
        unions = set(token.union_scopes)
        unions.add(tuple(sorted({str(term).strip().lower() for term in terms if str(term).strip()})))
        return self.replace_union_scopes(name, unions)

    def unbind_union(self, name, *terms):
        token = self.require(name)
        target = tuple(sorted({str(term).strip().lower() for term in terms if str(term).strip()}))
        unions = set(token.union_scopes)
        unions.discard(target)
        return self.replace_union_scopes(name, unions)

    def _effective_authority(self, token, *, readonly):
        exact = self.scopes.resolve(token.scopes, readonly=readonly)
        operations = set(exact.operations)
        leaves = self.scopes.all(readonly=readonly)
        for union_terms in token.union_scopes:
            operations.update(resolve_semantic(leaves, union_terms).operations)
        return EffectiveScope(frozenset(operations), exact.environment)

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
                union_scopes=token.union_scopes,
            )
        return AuthenticatedToken(token, authority)
