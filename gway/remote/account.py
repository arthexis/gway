"""Browser account-linking and consent behavior for remote access."""

from html import escape
import secrets

from ..security.oauth import OAuthRegistry
from ..security.tokens import AuthenticationError, TokenRegistry
from .session import RemoteSessionStore


def _page(title, body):
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        f"<title>{escape(title)}</title></head><body>{body}</body></html>"
    )


OPERATION_PREVIEW_LIMIT = 6


def _scopes(value):
    if value is None:
        return frozenset()
    if isinstance(value, str):
        values = value.split()
    else:
        values = value
    return frozenset(str(item).strip() for item in values if str(item).strip())


class RemoteAccountApplication:
    """One-user browser linking and consent layer over G-Way security."""

    def __init__(
        self,
        *,
        oauth=None,
        tokens=None,
        sessions=None,
        operation_resolver=None,
    ):
        self.oauth = OAuthRegistry() if oauth is None else oauth
        self.tokens = TokenRegistry(self.oauth.path) if tokens is None else tokens
        self.sessions = RemoteSessionStore() if sessions is None else sessions
        self.operation_resolver = operation_resolver

    def new_session(self):
        return self.sessions.create()

    def stage_consent(self, session, client_id, scopes, *, resource=None):
        client_id = str(client_id or "").strip()
        if not client_id:
            raise ValueError("OAuth client id is required")
        scopes = _scopes(scopes)
        if not scopes:
            raise ValueError("At least one named G-Way scope is required")
        session.pending_client_id = client_id
        session.pending_scopes = scopes
        session.pending_resource = None if resource is None else str(resource).strip()
        session.approved_grant_id = None
        return session

    def connect_page(self, session):
        return _page(
            "Connect G-Way",
            "<h1>Connect G-Way</h1>"
            "<p>Enter a G-Way bearer once to link this browser session. "
            "The bearer is verified and discarded.</p>"
            '<form method="post" action="/connect">'
            f'<input type="hidden" name="csrf" value="{escape(session.csrf)}">'
            '<label>Bearer <input type="password" name="bearer" '
            'autocomplete="off" required></label>'
            '<button type="submit">Connect</button></form>',
        )

    def connect(self, session, *, csrf, bearer):
        if not secrets.compare_digest(session.csrf, str(csrf or "")):
            raise PermissionError("Invalid CSRF token")
        try:
            identity = self.tokens.authenticate(str(bearer or ""))
        except AuthenticationError:
            raise PermissionError("Invalid bearer token") from None

        # The random link identifier is safe metadata. The raw bearer is never stored.
        link_name = f"remote-{secrets.token_hex(12)}"
        self.oauth.link(link_name, identity.token.name)
        session.link_name = link_name
        session.approved_grant_id = None
        self.sessions.rotate(session)
        return self.oauth.get_link(link_name)

    def _operation_mutates(self, name):
        if self.operation_resolver is None:
            return True
        operation = self.operation_resolver(name)
        if operation is None:
            return True
        return bool(getattr(operation, "mutates", True))

    def permission_summary(self, scope_names):
        names = frozenset(scope_names)
        operations = set()
        environment = set()
        scope_summaries = []

        for name in sorted(names):
            scope = self.oauth.scopes.require(name)
            scope_operations = tuple(sorted(scope.operations))
            scope_environment = tuple(sorted(scope.environment))
            mutation_capable = any(
                self._operation_mutates(operation) for operation in scope_operations
            )
            scope_summaries.append(
                {
                    "name": name,
                    "operation_count": len(scope_operations),
                    "operations": scope_operations,
                    "operations_preview": scope_operations[:OPERATION_PREVIEW_LIMIT],
                    "remaining_operations": max(
                        0, len(scope_operations) - OPERATION_PREVIEW_LIMIT
                    ),
                    "environment_count": len(scope_environment),
                    "environment": scope_environment,
                    "mutation_capable": mutation_capable,
                }
            )
            operations.update(scope_operations)
            environment.update(scope_environment)

        effective_operations = tuple(sorted(operations))
        effective_environment = tuple(sorted(environment))
        return {
            "scopes": tuple(scope_summaries),
            "effective": {
                "scope_count": len(names),
                "operation_count": len(effective_operations),
                "operations": effective_operations,
                "environment_count": len(effective_environment),
                "environment": effective_environment,
                "mutation_capable": any(
                    self._operation_mutates(operation)
                    for operation in effective_operations
                ),
            },
        }

    def consent_details(self, session):
        if not session.link_name:
            raise PermissionError("G-Way connection required")
        if not session.pending_client_id or not session.pending_scopes:
            raise ValueError("No pending consent request")

        link = self.oauth.get_link(session.link_name)
        if link is None or link.revoked_at is not None:
            raise PermissionError("G-Way connection is revoked")
        token = self.tokens.require(link.token_name)
        bearer_scopes = frozenset(token.scopes)
        if not bearer_scopes:
            raise PermissionError("Linked bearer has no scopes")

        missing_requested = session.pending_scopes - bearer_scopes
        if missing_requested:
            raise PermissionError(
                "Requested scopes are not available from the linked bearer: "
                + ", ".join(sorted(missing_requested))
            )

        operations = set()
        environment = set()
        for name in sorted(bearer_scopes):
            scope = self.oauth.scopes.require(name)
            operations.update(scope.operations)
            environment.update(scope.environment)

        return {
            "client_id": session.pending_client_id,
            "resource": session.pending_resource,
            "scopes": bearer_scopes,
            "requested_scopes": frozenset(session.pending_scopes),
            "operations": frozenset(operations),
            "environment": frozenset(environment),
            "permission_summary": self.permission_summary(bearer_scopes),
        }

    @staticmethod
    def _scope_details(item):
        preview = ", ".join(escape(operation) for operation in item["operations_preview"])
        preview_html = (
            f"<div><code>{preview}</code>"
            + (
                f" …and {item['remaining_operations']} more"
                if item["remaining_operations"]
                else ""
            )
            + "</div>"
            if preview
            else "<div>No operations</div>"
        )
        all_operations = ", ".join(escape(operation) for operation in item["operations"])
        expand_html = (
            "<details>"
            f"<summary>See all {item['operation_count']} operations</summary>"
            f"<div><code>{all_operations}</code></div>"
            "</details>"
            if item["remaining_operations"]
            else ""
        )
        return (
            "<li>"
            f"<strong>{escape(item['name'])}</strong>"
            f"<div>{item['operation_count']} operations; "
            + ("includes state changes" if item["mutation_capable"] else "read-only")
            + f"; {item['environment_count']} environment names</div>"
            + preview_html
            + expand_html
            + "</li>"
        )

    def consent_page(self, session):
        details = self.consent_details(session)
        summary = details["permission_summary"]
        scope_items = "".join(self._scope_details(item) for item in summary["scopes"])
        environment_items = "".join(
            f"<li>{escape(name)}</li>" for name in sorted(details["environment"])
        )
        if not environment_items:
            environment_items = "<li>None</li>"
        effective = summary["effective"]
        resource = (
            f"<p>Resource: <code>{escape(details['resource'])}</code></p>"
            if details["resource"]
            else ""
        )
        return _page(
            "Remote access consent",
            "<h1>Authorize remote access</h1>"
            f"<p>Client: <code>{escape(details['client_id'])}</code></p>"
            + resource
            + "<p>The linked bearer defines the maximum G-Way authority for this "
            "connection. This page is informational; scopes are not edited here.</p>"
            f"<h2>Bearer scopes</h2><ul>{scope_items}</ul>"
            "<h2>Effective access</h2>"
            f"<p>{effective['operation_count']} unique operations; "
            + (
                "includes state changes"
                if effective["mutation_capable"]
                else "read-only"
            )
            + f"; {effective['environment_count']} environment names</p>"
            f"<h2>Environment</h2><ul>{environment_items}</ul>"
            '<form method="post" action="/consent">'
            f'<input type="hidden" name="csrf" value="{escape(session.csrf)}">'
            '<button name="decision" value="approve" type="submit">Authorize</button>'
            '<button name="decision" value="deny" type="submit">Deny</button>'
            "</form>",
        )

    def decide_consent(self, session, *, csrf, decision):
        if not secrets.compare_digest(session.csrf, str(csrf or "")):
            raise PermissionError("Invalid CSRF token")
        decision = str(decision or "").strip().casefold()
        if decision not in {"approve", "deny"}:
            raise ValueError("Consent decision must be approve or deny")

        details = self.consent_details(session)
        grant = None
        if decision == "approve":
            grant = self.oauth.create_grant(
                session.link_name,
                details["client_id"],
                scopes=details["scopes"],
                resource=details["resource"],
            )
            session.approved_grant_id = grant.id
        else:
            session.approved_grant_id = None

        session.pending_client_id = None
        session.pending_scopes = frozenset()
        session.pending_resource = None
        self.sessions.rotate_csrf(session)
        return grant

    def connections_page(self, session):
        if not session.link_name:
            state = "<p>No G-Way connection is linked.</p>"
        else:
            link = self.oauth.get_link(session.link_name)
            if link is None:
                state = "<p>No G-Way connection is linked.</p>"
            else:
                status = "revoked" if link.revoked_at else "connected"
                state = (
                    f"<p>Connection: <strong>{escape(status)}</strong></p>"
                    f"<p>Token identity: <code>{escape(link.token_name)}</code></p>"
                )
        return _page(
            "Remote connections",
            "<h1>Remote connections</h1>"
            + state
            + (
                '<form method="post" action="/settings/connections">'
                f'<input type="hidden" name="csrf" value="{escape(session.csrf)}">'
                '<button name="action" value="revoke" type="submit">Revoke</button>'
                "</form>"
                if session.link_name
                else ""
            ),
        )

    def revoke_connection(self, session, *, csrf):
        if not secrets.compare_digest(session.csrf, str(csrf or "")):
            raise PermissionError("Invalid CSRF token")
        if not session.link_name:
            return False
        link = self.oauth.get_link(session.link_name)
        if link is None:
            session.link_name = None
            return False
        self.oauth.revoke_link(session.link_name)
        session.link_name = None
        session.approved_grant_id = None
        session.pending_client_id = None
        session.pending_scopes = frozenset()
        session.pending_resource = None
        session.pending_redirect_uri = None
        session.pending_state = None
        session.pending_code_challenge = None
        self.sessions.rotate_csrf(session)
        return True
