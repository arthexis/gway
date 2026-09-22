"""Persistent OAuth security state layered over G-Way named scopes."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import base64
import hashlib
import json
import secrets

from ..cache import default_root
from .scopes import EffectiveScope, ScopeRegistry
from .state import SecurityState
from .tokens import TokenRegistry


class OAuthAuthenticationError(PermissionError):
    """Raised when an OAuth credential cannot be authenticated."""

    def __init__(self):
        super().__init__("Invalid OAuth credential")


@dataclass(frozen=True)
class OAuthClient:
    client_id: str
    redirect_uris: frozenset[str]
    metadata_url: str | None
    disabled: bool
    created_at: str


@dataclass(frozen=True)
class OAuthLink:
    name: str
    token_name: str
    created_at: str
    revoked_at: str | None = None


@dataclass(frozen=True)
class OAuthGrant:
    id: int
    link_name: str
    client_id: str
    resource: str | None
    scopes: frozenset[str]
    created_at: str
    revoked_at: str | None = None


@dataclass(frozen=True)
class IssuedAuthorizationCode:
    grant: OAuthGrant
    code: str
    redirect_uri: str
    expires_at: str


@dataclass(frozen=True)
class IssuedOAuthTokens:
    grant: OAuthGrant
    access_token: str
    access_expires_at: str
    refresh_token: str
    refresh_expires_at: str


@dataclass(frozen=True)
class AuthenticatedOAuthToken:
    grant: OAuthGrant
    authority: EffectiveScope


class OAuthRegistry:
    """OAuth persistence whose effective authority remains G-Way scope policy."""

    def __init__(self, path=None):
        path = default_root() / "security" / "state.sqlite" if path is None else path
        self.state = SecurityState(path)
        self.scopes = ScopeRegistry(path)
        self.tokens = TokenRegistry(path)

    @property
    def path(self):
        return self.state.path

    @staticmethod
    def _text(value, label):
        value = str(value).strip()
        if not value:
            raise ValueError(f"{label} must be a non-empty string")
        return value

    @staticmethod
    def _now():
        return datetime.now(timezone.utc)

    @staticmethod
    def _hash(value):
        return hashlib.sha256(str(value).encode("utf-8")).hexdigest()

    @staticmethod
    def _expiry(seconds):
        seconds = int(seconds)
        if seconds <= 0:
            raise ValueError("OAuth credential lifetime must be positive")
        return (OAuthRegistry._now() + timedelta(seconds=seconds)).isoformat()

    @staticmethod
    def _secret(prefix):
        public_id = secrets.token_hex(8)
        secret = secrets.token_urlsafe(32)
        return public_id, f"{prefix}_{public_id}_{secret}"

    @staticmethod
    def _public_id(value, prefix):
        try:
            actual, public_id, secret = str(value).split("_", 2)
        except ValueError:
            raise OAuthAuthenticationError() from None
        if actual != prefix or not public_id or not secret:
            raise OAuthAuthenticationError()
        return public_id

    @staticmethod
    def _pkce(verifier):
        digest = hashlib.sha256(str(verifier).encode("ascii")).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")

    def create_client(self, client_id, *, redirect_uris=(), metadata_url=None):
        client_id = self._text(client_id, "OAuth client id")
        redirects = frozenset(
            self._text(uri, "OAuth redirect URI") for uri in redirect_uris
        )
        created_at = self._now().isoformat()
        with self.state.connect() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO oauth_clients (
                        client_id, metadata_url, redirect_uris, created_at, disabled
                    ) VALUES (?, ?, ?, ?, 0)
                    """,
                    (
                        client_id,
                        None if metadata_url is None else str(metadata_url),
                        json.dumps(sorted(redirects)),
                        created_at,
                    ),
                )
            except Exception:
                if connection.execute(
                    "SELECT 1 FROM oauth_clients WHERE client_id = ?", (client_id,)
                ).fetchone():
                    raise ValueError(f"OAuth client already exists: {client_id}") from None
                raise
        return self.get_client(client_id)

    def get_client(self, client_id):
        if not self.path.is_file():
            return None
        client_id = self._text(client_id, "OAuth client id")
        with self.state.connect() as connection:
            row = connection.execute(
                """
                SELECT client_id, metadata_url, redirect_uris, created_at, disabled
                FROM oauth_clients WHERE client_id = ?
                """,
                (client_id,),
            ).fetchone()
        if row is None:
            return None
        return OAuthClient(
            row["client_id"],
            frozenset(json.loads(row["redirect_uris"])),
            row["metadata_url"],
            bool(row["disabled"]),
            row["created_at"],
        )

    def link(self, name, token_name):
        name = self._text(name, "OAuth link name")
        token = self.tokens.require(token_name)
        created_at = self._now().isoformat()
        with self.state.connect() as connection:
            token_row = connection.execute(
                "SELECT id FROM tokens WHERE name = ?", (token.name,)
            ).fetchone()
            try:
                connection.execute(
                    """
                    INSERT INTO oauth_links (name, token_id, created_at, revoked_at)
                    VALUES (?, ?, ?, NULL)
                    """,
                    (name, token_row["id"], created_at),
                )
            except Exception:
                if connection.execute(
                    "SELECT 1 FROM oauth_links WHERE name = ?", (name,)
                ).fetchone():
                    raise ValueError(f"OAuth link already exists: {name}") from None
                raise
        return self.get_link(name)

    def get_link(self, name):
        if not self.path.is_file():
            return None
        name = self._text(name, "OAuth link name")
        with self.state.connect() as connection:
            row = connection.execute(
                """
                SELECT oauth_links.name, tokens.name AS token_name,
                       oauth_links.created_at, oauth_links.revoked_at
                FROM oauth_links
                JOIN tokens ON tokens.id = oauth_links.token_id
                WHERE oauth_links.name = ?
                """,
                (name,),
            ).fetchone()
        if row is None:
            return None
        return OAuthLink(
            row["name"], row["token_name"], row["created_at"], row["revoked_at"]
        )

    def revoke_link(self, name):
        name = self._text(name, "OAuth link name")
        revoked_at = self._now().isoformat()
        with self.state.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE oauth_links
                SET revoked_at = COALESCE(revoked_at, ?)
                WHERE name = ?
                """,
                (revoked_at, name),
            )
            if not cursor.rowcount:
                raise LookupError(f"Unknown OAuth link: {name}")
        return self.get_link(name)

    @staticmethod
    def _grant_scopes(connection, grant_id):
        return frozenset(
            row["name"]
            for row in connection.execute(
                """
                SELECT scopes.name
                FROM oauth_grant_scopes
                JOIN scopes ON scopes.id = oauth_grant_scopes.scope_id
                WHERE oauth_grant_scopes.grant_id = ?
                ORDER BY scopes.name
                """,
                (grant_id,),
            )
        )

    @classmethod
    def _grant_from_row(cls, connection, row):
        if row is None:
            return None
        return OAuthGrant(
            row["id"],
            row["link_name"],
            row["client_id"],
            row["resource"],
            cls._grant_scopes(connection, row["id"]),
            row["created_at"],
            row["revoked_at"],
        )

    def get_grant(self, grant_id):
        if not self.path.is_file():
            return None
        with self.state.connect() as connection:
            row = connection.execute(
                """
                SELECT oauth_grants.id, oauth_links.name AS link_name,
                       oauth_grants.client_id, oauth_grants.resource,
                       oauth_grants.created_at, oauth_grants.revoked_at
                FROM oauth_grants
                JOIN oauth_links ON oauth_links.id = oauth_grants.link_id
                WHERE oauth_grants.id = ?
                """,
                (int(grant_id),),
            ).fetchone()
            return self._grant_from_row(connection, row)

    def create_grant(self, link_name, client_id, *, scopes, resource=None):
        link_name = self._text(link_name, "OAuth link name")
        client_id = self._text(client_id, "OAuth client id")
        resource = None if resource is None else self._text(resource, "OAuth resource")
        link = self.get_link(link_name)
        if link is None:
            raise LookupError(f"Unknown OAuth link: {link_name}")
        if link.revoked_at is not None:
            raise ValueError(f"OAuth link is revoked: {link_name}")
        token = self.tokens.require(link.token_name)
        scope_names = frozenset(self._text(name, "scope name") for name in scopes)
        unknown = scope_names - token.scopes
        if unknown:
            raise ValueError(
                "OAuth grant exceeds linked token scopes: "
                + ", ".join(sorted(unknown))
            )
        for name in scope_names:
            self.scopes.require(name)

        with self.state.connect() as connection:
            link_row = connection.execute(
                "SELECT id FROM oauth_links WHERE name = ?", (link_name,)
            ).fetchone()
            cursor = connection.execute(
                """
                INSERT INTO oauth_grants (
                    link_id, client_id, resource, created_at, revoked_at
                ) VALUES (?, ?, ?, ?, NULL)
                """,
                (
                    link_row["id"],
                    client_id,
                    resource,
                    self._now().isoformat(),
                ),
            )
            grant_id = cursor.lastrowid
            for name in sorted(scope_names):
                scope = connection.execute(
                    "SELECT id FROM scopes WHERE name = ?", (name,)
                ).fetchone()
                connection.execute(
                    """
                    INSERT INTO oauth_grant_scopes (grant_id, scope_id)
                    VALUES (?, ?)
                    """,
                    (grant_id, scope["id"]),
                )
        return self.get_grant(grant_id)

    def revoke_grant(self, grant_id):
        revoked_at = self._now().isoformat()
        with self.state.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE oauth_grants
                SET revoked_at = COALESCE(revoked_at, ?)
                WHERE id = ?
                """,
                (revoked_at, int(grant_id)),
            )
            if not cursor.rowcount:
                raise LookupError(f"Unknown OAuth grant: {grant_id}")
        return self.get_grant(grant_id)

    def _active_grant(self, connection, grant_id):
        row = connection.execute(
            """
            SELECT oauth_grants.id, oauth_links.name AS link_name,
                   oauth_grants.client_id, oauth_grants.resource,
                   oauth_grants.created_at, oauth_grants.revoked_at,
                   oauth_links.revoked_at AS link_revoked_at,
                   tokens.name AS token_name, tokens.disabled AS token_disabled,
                   tokens.expires_at AS token_expires_at
            FROM oauth_grants
            JOIN oauth_links ON oauth_links.id = oauth_grants.link_id
            JOIN tokens ON tokens.id = oauth_links.token_id
            WHERE oauth_grants.id = ?
            """,
            (int(grant_id),),
        ).fetchone()
        if row is None or row["revoked_at"] is not None or row["link_revoked_at"] is not None:
            raise OAuthAuthenticationError()
        if bool(row["token_disabled"]):
            raise OAuthAuthenticationError()
        if row["token_expires_at"] is not None:
            if datetime.fromisoformat(row["token_expires_at"]) <= self._now():
                raise OAuthAuthenticationError()
        return row

    def _effective_grant(self, connection, grant_id):
        row = self._active_grant(connection, grant_id)
        granted = self._grant_scopes(connection, grant_id)
        current_token_scopes = frozenset(
            item["name"]
            for item in connection.execute(
                """
                SELECT scopes.name
                FROM oauth_links
                JOIN token_scopes ON token_scopes.token_id = oauth_links.token_id
                JOIN scopes ON scopes.id = token_scopes.scope_id
                WHERE oauth_links.name = ?
                """,
                (row["link_name"],),
            )
        )
        scope_names = granted & current_token_scopes
        grant = OAuthGrant(
            row["id"],
            row["link_name"],
            row["client_id"],
            row["resource"],
            granted,
            row["created_at"],
            row["revoked_at"],
        )
        return grant, self.scopes.resolve(scope_names)

    def issue_authorization_code(
        self,
        grant_id,
        *,
        redirect_uri,
        code_challenge,
        lifetime_seconds=300,
    ):
        redirect_uri = self._text(redirect_uri, "OAuth redirect URI")
        code_challenge = self._text(code_challenge, "PKCE code challenge")
        public_id, code = self._secret("gwc")
        del public_id
        expires_at = self._expiry(lifetime_seconds)
        with self.state.connect() as connection:
            self._active_grant(connection, grant_id)
            connection.execute(
                """
                INSERT INTO oauth_authorization_codes (
                    grant_id, code_hash, redirect_uri, code_challenge,
                    code_challenge_method, created_at, expires_at, consumed_at
                ) VALUES (?, ?, ?, ?, 'S256', ?, ?, NULL)
                """,
                (
                    int(grant_id),
                    self._hash(code),
                    redirect_uri,
                    code_challenge,
                    self._now().isoformat(),
                    expires_at,
                ),
            )
        return IssuedAuthorizationCode(
            self.get_grant(grant_id), code, redirect_uri, expires_at
        )

    def consume_authorization_code(
        self,
        code,
        *,
        redirect_uri,
        code_verifier,
        client_id=None,
        resource=None,
    ):
        redirect_uri = self._text(redirect_uri, "OAuth redirect URI")
        code_verifier = self._text(code_verifier, "PKCE code verifier")
        client_id = (
            None if client_id is None else self._text(client_id, "OAuth client id")
        )
        resource = None if resource is None else self._text(resource, "OAuth resource")
        code_hash = self._hash(code)
        with self.state.connect() as connection:
            row = connection.execute(
                """
                SELECT id, grant_id, redirect_uri, code_challenge,
                       code_challenge_method, expires_at, consumed_at
                FROM oauth_authorization_codes
                WHERE code_hash = ?
                """,
                (code_hash,),
            ).fetchone()
            if row is None:
                raise OAuthAuthenticationError()
            if row["consumed_at"] is not None:
                raise OAuthAuthenticationError()
            if datetime.fromisoformat(row["expires_at"]) <= self._now():
                raise OAuthAuthenticationError()
            if row["redirect_uri"] != redirect_uri:
                raise OAuthAuthenticationError()
            if row["code_challenge_method"] != "S256":
                raise OAuthAuthenticationError()
            if not secrets.compare_digest(
                row["code_challenge"], self._pkce(code_verifier)
            ):
                raise OAuthAuthenticationError()
            active = self._active_grant(connection, row["grant_id"])
            if client_id is not None and active["client_id"] != client_id:
                raise OAuthAuthenticationError()
            if resource is not None and active["resource"] != resource:
                raise OAuthAuthenticationError()
            consumed_at = self._now().isoformat()
            cursor = connection.execute(
                """
                UPDATE oauth_authorization_codes
                SET consumed_at = ?
                WHERE id = ? AND consumed_at IS NULL
                """,
                (consumed_at, row["id"]),
            )
            if cursor.rowcount != 1:
                raise OAuthAuthenticationError()
            grant_id = row["grant_id"]
        return self.get_grant(grant_id)

    def issue_tokens(
        self,
        grant_id,
        *,
        access_lifetime_seconds=900,
        refresh_lifetime_seconds=2592000,
    ):
        access_public, access = self._secret("gwa")
        refresh_public, refresh = self._secret("gwr")
        access_expires = self._expiry(access_lifetime_seconds)
        refresh_expires = self._expiry(refresh_lifetime_seconds)
        created_at = self._now().isoformat()
        with self.state.connect() as connection:
            self._active_grant(connection, grant_id)
            connection.execute(
                """
                INSERT INTO oauth_access_tokens (
                    grant_id, public_id, token_hash, created_at, expires_at, revoked_at
                ) VALUES (?, ?, ?, ?, ?, NULL)
                """,
                (
                    int(grant_id),
                    access_public,
                    self._hash(access),
                    created_at,
                    access_expires,
                ),
            )
            connection.execute(
                """
                INSERT INTO oauth_refresh_tokens (
                    grant_id, public_id, token_hash, created_at, expires_at,
                    revoked_at, rotated_at
                ) VALUES (?, ?, ?, ?, ?, NULL, NULL)
                """,
                (
                    int(grant_id),
                    refresh_public,
                    self._hash(refresh),
                    created_at,
                    refresh_expires,
                ),
            )
        return IssuedOAuthTokens(
            self.get_grant(grant_id),
            access,
            access_expires,
            refresh,
            refresh_expires,
        )

    def authenticate_access(self, bearer):
        public_id = self._public_id(bearer, "gwa")
        with self.state.connect() as connection:
            row = connection.execute(
                """
                SELECT grant_id, token_hash, expires_at, revoked_at
                FROM oauth_access_tokens WHERE public_id = ?
                """,
                (public_id,),
            ).fetchone()
            if (
                row is None
                or row["revoked_at"] is not None
                or datetime.fromisoformat(row["expires_at"]) <= self._now()
                or not secrets.compare_digest(row["token_hash"], self._hash(bearer))
            ):
                raise OAuthAuthenticationError()
            grant, authority = self._effective_grant(connection, row["grant_id"])
        return AuthenticatedOAuthToken(grant, authority)

    def rotate_refresh(
        self,
        refresh_token,
        *,
        client_id=None,
        resource=None,
        access_lifetime_seconds=900,
        refresh_lifetime_seconds=2592000,
    ):
        client_id = (
            None if client_id is None else self._text(client_id, "OAuth client id")
        )
        resource = None if resource is None else self._text(resource, "OAuth resource")
        public_id = self._public_id(refresh_token, "gwr")
        with self.state.connect() as connection:
            row = connection.execute(
                """
                SELECT id, grant_id, token_hash, expires_at, revoked_at, rotated_at
                FROM oauth_refresh_tokens WHERE public_id = ?
                """,
                (public_id,),
            ).fetchone()
            if (
                row is None
                or row["revoked_at"] is not None
                or row["rotated_at"] is not None
                or datetime.fromisoformat(row["expires_at"]) <= self._now()
                or not secrets.compare_digest(
                    row["token_hash"], self._hash(refresh_token)
                )
            ):
                raise OAuthAuthenticationError()
            active = self._active_grant(connection, row["grant_id"])
            if client_id is not None and active["client_id"] != client_id:
                raise OAuthAuthenticationError()
            if resource is not None and active["resource"] != resource:
                raise OAuthAuthenticationError()
            rotated_at = self._now().isoformat()
            cursor = connection.execute(
                """
                UPDATE oauth_refresh_tokens
                SET rotated_at = ?
                WHERE id = ? AND rotated_at IS NULL AND revoked_at IS NULL
                """,
                (rotated_at, row["id"]),
            )
            if cursor.rowcount != 1:
                raise OAuthAuthenticationError()
            grant_id = row["grant_id"]
        return self.issue_tokens(
            grant_id,
            access_lifetime_seconds=access_lifetime_seconds,
            refresh_lifetime_seconds=refresh_lifetime_seconds,
        )

    def revoke(self, bearer):
        value = str(bearer)
        if value.startswith("gwa_"):
            public_id = self._public_id(value, "gwa")
            table = "oauth_access_tokens"
        elif value.startswith("gwr_"):
            public_id = self._public_id(value, "gwr")
            table = "oauth_refresh_tokens"
        else:
            raise OAuthAuthenticationError()
        with self.state.connect() as connection:
            cursor = connection.execute(
                f"""
                UPDATE {table}
                SET revoked_at = COALESCE(revoked_at, ?)
                WHERE public_id = ? AND token_hash = ?
                """,
                (self._now().isoformat(), public_id, self._hash(value)),
            )
        return bool(cursor.rowcount)
