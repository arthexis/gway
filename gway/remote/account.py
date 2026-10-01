"""Browser account-linking and consent behavior for remote access."""

from html import escape
import secrets

from ..security.oauth import OAuthRegistry
from ..security.semantics import resolve as resolve_semantic
from ..security.tokens import AuthenticationError, TokenRegistry
from .session import RemoteSessionStore


def _page(title, body):
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<meta name="color-scheme" content="dark">'
        f"<title>{escape(title)}</title>"
        '<link rel="stylesheet" href="/remote.css">'
        "</head><body><main>"
        f"{body}</main></body></html>"
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


def _union_scopes(value):
    if value is None:
        return frozenset()
    values = (
        [item for item in value.split(";") if item.strip()]
        if isinstance(value, str)
        else value
    )
    result = set()
    for expression in values:
        raw = expression.replace(",", " ").split() if isinstance(expression, str) else expression
        terms = tuple(
            sorted(
                {
                    str(term).strip().lower()
                    for term in raw
                    if str(term).strip()
                }
            )
        )
        if not terms:
            raise ValueError("union scope requires at least one semantic term")
        result.add(terms)
    return frozenset(result)


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

    def stage_consent(
        self,
        session,
        client_id,
        scopes=None,
        *,
        union_scopes=None,
        resource=None,
    ):
        client_id = str(client_id or "").strip()
        if not client_id:
            raise ValueError("OAuth client id is required")
        exact = _scopes(scopes)
        unions = _union_scopes(union_scopes)
        session.pending_client_id = client_id
        session.pending_scopes = exact
        session.pending_union_scopes = unions
        session.pending_resource = None if resource is None else str(resource).strip()
        session.approved_grant_id = None
        return session

    def connect_context(self, session):
        return {"csrf": escape(session.csrf, quote=True)}

    def connect_page(self, session):
        context = self.connect_context(session)
        return _page(
            "Connect G-Way",
            "<h1>Connect G-Way</h1>"
            "<p>Enter a G-Way bearer once to link this browser session. "
            "The bearer is verified and discarded.</p>"
            '<form method="post" action="/connect">'
            f'<input type="hidden" name="csrf" value="{context["csrf"]}">'
            '<label for="bearer">Bearer</label><input id="bearer" type="password" name="bearer" '
            'autocomplete="off" autocapitalize="none" spellcheck="false" inputmode="text" required></label>'
            '<div class="actions"><button class="primary" type="submit">Connect securely</button></div></form>',
        )

    def connect(self, session, *, csrf, bearer):
        if not secrets.compare_digest(session.csrf, str(csrf or "")):
            raise PermissionError("Invalid CSRF token")
        try:
            identity = self.tokens.authenticate(str(bearer or ""))
        except AuthenticationError:
            raise PermissionError("Invalid bearer token") from None

        if (
            session.pending_client_id
            and not session.pending_scopes
            and not session.pending_union_scopes
        ):
            session.pending_scopes = identity.token.scopes

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
            all_operations = "__all__" in scope.operations
            all_environment = "__all__" in scope.environment
            mutation_capable = all_operations or any(
                self._operation_mutates(operation) for operation in scope_operations
            )
            scope_summaries.append(
                {
                    "name": name,
                    "operation_count": None if all_operations else len(scope_operations),
                    "all_operations": all_operations,
                    "operations": scope_operations,
                    "operations_preview": scope_operations[:OPERATION_PREVIEW_LIMIT],
                    "remaining_operations": max(
                        0, len(scope_operations) - OPERATION_PREVIEW_LIMIT
                    ),
                    "environment_count": None if all_environment else len(scope_environment),
                    "all_environment": all_environment,
                    "environment": scope_environment,
                    "mutation_capable": mutation_capable,
                }
            )
            operations.update(scope_operations)
            environment.update(scope_environment)

        effective_operations = tuple(sorted(operations))
        effective_environment = tuple(sorted(environment))
        effective_all_operations = "__all__" in operations
        effective_all_environment = "__all__" in environment
        return {
            "scopes": tuple(scope_summaries),
            "effective": {
                "scope_count": len(names),
                "operation_count": None if effective_all_operations else len(effective_operations),
                "all_operations": effective_all_operations,
                "operations": effective_operations,
                "environment_count": None if effective_all_environment else len(effective_environment),
                "all_environment": effective_all_environment,
                "environment": effective_environment,
                "mutation_capable": effective_all_operations or any(
                    self._operation_mutates(operation)
                    for operation in effective_operations
                ),
            },
        }

    def union_summary(self, union_scopes):
        leaves = self.oauth.scopes.all()
        summaries = []
        for union_terms in sorted(union_scopes):
            resolved = resolve_semantic(leaves, union_terms)
            operations = tuple(sorted(resolved.operations))
            summaries.append(
                {
                    "terms": tuple(sorted(resolved.terms)),
                    "exact_scopes": resolved.exact_scopes,
                    "conjunction": resolved.conjunction,
                    "matched_scopes": resolved.scopes,
                    "operations": operations,
                    "mutation_capable": any(
                        self._operation_mutates(operation) for operation in operations
                    ),
                }
            )
        return tuple(summaries)

    def consent_details(self, session):
        if not session.link_name:
            raise PermissionError("G-Way connection required")
        if not session.pending_client_id:
            raise ValueError("No pending consent request")

        link = self.oauth.get_link(session.link_name)
        if link is None or link.revoked_at is not None:
            raise PermissionError("G-Way connection is revoked")
        token = self.tokens.require(link.token_name)

        exact_scopes = frozenset(session.pending_scopes)
        union_scopes = frozenset(session.pending_union_scopes)
        if not exact_scopes and not union_scopes:
            raise PermissionError("Linked bearer grants no scopes")

        missing_requested = exact_scopes - token.scopes
        if missing_requested:
            raise PermissionError(
                "Requested scopes are not available from the linked bearer: "
                + ", ".join(sorted(missing_requested))
            )

        unavailable_unions = [
            terms
            for terms in union_scopes
            if not self.oauth._union_is_within(terms, token.union_scopes)
        ]
        if unavailable_unions:
            rendered = ", ".join(" + ".join(terms) for terms in sorted(unavailable_unions))
            raise PermissionError(
                "Requested union scopes are not available from the linked bearer: "
                + rendered
            )

        exact_summary = self.permission_summary(exact_scopes)
        union_summary = self.union_summary(union_scopes)
        operations = set(exact_summary["effective"]["operations"])
        for item in union_summary:
            operations.update(item["operations"])

        return {
            "client_id": session.pending_client_id,
            "resource": session.pending_resource,
            "scopes": exact_scopes,
            "union_scopes": union_scopes,
            "operations": frozenset(operations),
            "environment": frozenset(exact_summary["effective"]["environment"]),
            "permission_summary": exact_summary,
            "union_summary": union_summary,
        }

    @staticmethod
    def _scope_details(item):
        if item["all_operations"]:
            return (
                "<li>"
                f"<strong>{escape(item['name'])}</strong>"
                "<div>All current and future operations; includes state changes; "
                + (
                    "all current and future environment variables"
                    if item["all_environment"]
                    else f"{item['environment_count']} environment names"
                )
                + "</div><div><code>__all__</code></div></li>"
            )

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
            f"<div><code>{all_operations}</code></div></details>"
            if item["remaining_operations"]
            else ""
        )
        return (
            "<li>"
            f"<strong>{escape(item['name'])}</strong>"
            f"<div>{item['operation_count']} operations; "
            + ("includes state changes" if item["mutation_capable"] else "read-only")
            + (
                "; all current and future environment variables</div>"
                if item["all_environment"]
                else f"; {item['environment_count']} environment names</div>"
            )
            + preview_html
            + expand_html
            + "</li>"
        )

    @staticmethod
    def _union_details(item):
        terms = " + ".join(escape(term) for term in item["terms"])
        if item["exact_scopes"]:
            representation = "Exact semantic scope: " + ", ".join(
                escape(name) for name in item["exact_scopes"]
            )
        elif item["conjunction"]:
            representation = "Represented as: " + " AND ".join(
                escape(name) for name in item["conjunction"]
            )
        else:
            representation = "No named representation exists yet"
        matches = (
            ", ".join(escape(name) for name in item["matched_scopes"])
            if item["matched_scopes"]
            else "None currently"
        )
        return (
            "<li>"
            f"<strong>{terms}</strong>"
            f"<div>{representation}</div>"
            f"<div>Currently matches: {matches}</div>"
            "<div class=\"muted\">Future scopes matching all of these terms may also be included.</div>"
            "</li>"
        )

    def consent_context(self, session):
        details = self.consent_details(session)
        summary = details["permission_summary"]
        scope_items = "".join(self._scope_details(item) for item in summary["scopes"])
        if not scope_items:
            scope_items = "<li>None</li>"
        union_items = "".join(
            self._union_details(item) for item in details["union_summary"]
        )
        if not union_items:
            union_items = "<li>None</li>"

        effective = summary["effective"]
        effective_operations = set(effective["operations"])
        for item in details["union_summary"]:
            effective_operations.update(item["operations"])
        effective_all_operations = "__all__" in effective_operations
        mutation_capable = effective_all_operations or any(
            self._operation_mutates(operation) for operation in effective_operations
        )

        if effective["all_environment"]:
            environment_items = "<li>All current and future environment variables</li>"
            environment_summary = "All current and future environment variables"
        else:
            environment_items = "".join(
                f"<li>{escape(name)}</li>" for name in sorted(details["environment"])
            )
            if not environment_items:
                environment_items = "<li>None</li>"
            environment_summary = f"{effective['environment_count']} named variables"

        operations_summary = (
            "All current and future operations"
            if effective_all_operations
            else f"{len(effective_operations)} unique operations"
        )
        mutation_summary = (
            "includes state-changing operations" if mutation_capable else "read-only"
        )
        authority_notice = (
            f"{operations_summary}; {mutation_summary}; {environment_summary}."
        )
        resource_html = (
            f'<p class="meta muted">Resource: <code>{escape(details["resource"])}</code></p>'
            if details["resource"]
            else ""
        )
        return {
            "csrf": escape(session.csrf, quote=True),
            "client_id": escape(details["client_id"]),
            "resource_html": resource_html,
            "authority_notice": escape(authority_notice),
            "scope_items_html": scope_items,
            "union_items_html": union_items,
            "environment_items_html": environment_items,
        }

    def consent_page(self, session):
        context = self.consent_context(session)
        return _page(
            "Remote access consent",
            "<h1>Authorize remote access</h1>"
            f'<p>Client: <code>{context["client_id"]}</code></p>'
            + context["resource_html"]
            + f'<p>{context["authority_notice"]}</p>'
            + '<p>Authorization grants only the exact and union authority shown below.</p>'
            + f'<h2>Exact scopes</h2><ul>{context["scope_items_html"]}</ul>'
            + f'<h2>Union scopes</h2><ul>{context["union_items_html"]}</ul>'
            + f'<h2>Environment</h2><ul>{context["environment_items_html"]}</ul>'
            + '<form method="post" action="/consent">'
            + f'<input type="hidden" name="csrf" value="{context["csrf"]}">'
            + '<button name="decision" value="approve" type="submit">Authorize</button>'
            + '<button name="decision" value="deny" type="submit">Deny</button>'
            + "</form>",
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
                union_scopes=details["union_scopes"],
                resource=details["resource"],
            )
            session.approved_grant_id = grant.id
        else:
            session.approved_grant_id = None

        session.pending_client_id = None
        session.pending_scopes = frozenset()
        session.pending_union_scopes = frozenset()
        session.pending_resource = None
        self.sessions.rotate_csrf(session)
        return grant

    def connections_context(self, session):
        linked = False
        if not session.link_name:
            connection_html = '<p class="muted">No G-Way connection is linked.</p>'
        else:
            link = self.oauth.get_link(session.link_name)
            if link is None:
                connection_html = '<p class="muted">No G-Way connection is linked.</p>'
            else:
                linked = True
                status = "revoked" if link.revoked_at else "connected"
                connection_html = (
                    f'<div class="summary"><strong>Connection</strong>{escape(status)}</div>'
                    f'<div class="summary"><strong>Token identity</strong>'
                    f'<code>{escape(link.token_name)}</code></div>'
                )
        revoke_form_html = ""
        if linked:
            revoke_form_html = (
                '<form method="post" action="/settings/connections">'
                f'<input type="hidden" name="csrf" value="{escape(session.csrf, quote=True)}">'
                '<div class="actions"><button class="danger" name="action" '
                'value="revoke" type="submit">Revoke connection</button></div></form>'
            )
        return {
            "connection_html": connection_html,
            "revoke_form_html": revoke_form_html,
        }

    def connections_page(self, session):
        context = self.connections_context(session)
        return _page(
            "Remote connections",
            "<h1>Remote connections</h1>"
            + context["connection_html"]
            + context["revoke_form_html"],
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
        session.pending_union_scopes = frozenset()
        session.pending_resource = None
        session.pending_redirect_uri = None
        session.pending_state = None
        session.pending_code_challenge = None
        self.sessions.rotate_csrf(session)
        return True