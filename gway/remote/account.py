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


def _scopes(value):
    if value is None:
        return frozenset()
    if isinstance(value, str):
        values = value.split()
    else:
        values = value
    result = frozenset(str(item).strip() for item in values if str(item).strip())
    return result


class RemoteAccountApplication:
    """One-user browser linking and consent layer over G-Way security."""

    def __init__(
        self,
        *,
        oauth=None,
        tokens=None,
        sessions=None,
    ):
        self.oauth = OAuthRegistry() if oauth is None else oauth
        self.tokens = TokenRegistry(self.oauth.path) if tokens is None else tokens
        self.sessions = RemoteSessionStore() if sessions is None else sessions

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
        session.requested_scopes = scopes
        # Until S2 adds explicit scope selection, preserve the existing consent
        # behavior with a provisional selection constrained by any linked bearer.
        session.selected_scopes = (
            scopes & session.available_scopes if session.link_name else scopes
        )
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
        session.available_scopes = frozenset(identity.token.scopes)
        if session.requested_scopes:
            session.selected_scopes = (
                session.requested_scopes & session.available_scopes
            )
        session.approved_grant_id = None
        self.sessions.rotate(session)
        return self.oauth.get_link(link_name)

    def consent_details(self, session):
        if not session.link_name:
            raise PermissionError("G-Way connection required")
        if not session.pending_client_id or not session.requested_scopes:
            raise ValueError("No pending consent request")
        if not session.selected_scopes:
            raise ValueError("No scopes selected for consent")

        link = self.oauth.get_link(session.link_name)
        if link is None or link.revoked_at is not None:
            raise PermissionError("G-Way connection is revoked")
        token = self.tokens.require(link.token_name)
        current_scopes = frozenset(token.scopes)
        session.available_scopes = current_scopes

        invalid_selection = session.selected_scopes - session.requested_scopes
        if invalid_selection:
            raise PermissionError(
                "Selected scopes were not requested: "
                + ", ".join(sorted(invalid_selection))
            )

        unavailable_selected = session.selected_scopes - current_scopes
        if unavailable_selected:
            raise PermissionError(
                "Selected scopes are no longer available: "
                + ", ".join(sorted(unavailable_selected))
            )

        operations = set()
        environment = set()
        for name in sorted(session.selected_scopes):
            scope = self.oauth.scopes.require(name)
            operations.update(scope.operations)
            environment.update(scope.environment)
        return {
            "client_id": session.pending_client_id,
            "resource": session.pending_resource,
            "scopes": frozenset(session.selected_scopes),
            "available_scopes": frozenset(session.available_scopes),
            "requested_scopes": frozenset(session.requested_scopes),
            "operations": frozenset(operations),
            "environment": frozenset(environment),
        }

    def select_scopes(self, session, scopes):
        scopes = _scopes(scopes)
        if not scopes:
            raise ValueError("At least one scope must be selected")
        if not session.link_name:
            raise PermissionError("G-Way connection required")
        if not session.pending_client_id or not session.requested_scopes:
            raise ValueError("No pending consent request")

        link = self.oauth.get_link(session.link_name)
        if link is None or link.revoked_at is not None:
            raise PermissionError("G-Way connection is revoked")
        token = self.tokens.require(link.token_name)
        current_scopes = frozenset(token.scopes)
        session.available_scopes = current_scopes

        candidates = session.requested_scopes & current_scopes
        invalid = scopes - candidates
        if invalid:
            raise PermissionError(
                "Selected scopes are not delegable: " + ", ".join(sorted(invalid))
            )
        session.selected_scopes = scopes
        return scopes

    def consent_page(self, session):
        details = self.consent_details(session)
        candidates = details["requested_scopes"] & details["available_scopes"]
        selected = details["scopes"]
        scope_items = "".join(
            "<li><label>"
            f'<input type="checkbox" name="scope" value="{escape(name)}"'
            + (" checked" if name in selected else "")
            + f"> {escape(name)}</label></li>"
            for name in sorted(candidates)
        )
        operation_items = "".join(
            f"<li>{escape(name)}</li>" for name in sorted(details["operations"])
        )
        environment_items = "".join(
            f"<li>{escape(name)}</li>" for name in sorted(details["environment"])
        )
        if not environment_items:
            environment_items = "<li>None</li>"
        return _page(
            "Remote access consent",
            "<h1>Authorize remote access</h1>"
            f"<p>Client: <code>{escape(details['client_id'])}</code></p>"
            f"<h2>Named scopes</h2><ul>{scope_items}</ul>"
            f"<h2>Operations</h2><ul>{operation_items}</ul>"
            f"<h2>Environment</h2><ul>{environment_items}</ul>"
            '<form method="post" action="/consent">'
            f'<input type="hidden" name="csrf" value="{escape(session.csrf)}">'
            '<button name="decision" value="approve" type="submit">Approve</button>'
            '<button name="decision" value="deny" type="submit">Deny</button>'
            "</form>",
        )

    def decide_consent(self, session, *, csrf, decision, scopes=None):
        if not secrets.compare_digest(session.csrf, str(csrf or "")):
            raise PermissionError("Invalid CSRF token")
        decision = str(decision or "").strip().casefold()
        if decision not in {"approve", "deny"}:
            raise ValueError("Consent decision must be approve or deny")

        if decision == "approve":
            self.select_scopes(session, scopes)
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
        session.requested_scopes = frozenset()
        session.selected_scopes = frozenset()
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
        session.available_scopes = frozenset()
        session.requested_scopes = frozenset()
        session.selected_scopes = frozenset()
        session.pending_resource = None
        session.pending_redirect_uri = None
        session.pending_state = None
        session.pending_code_challenge = None
        self.sessions.rotate_csrf(session)
        return True
