import sqlite3

import pytest

from gway.remote.account import RemoteAccountApplication
from gway.remote.session import RemoteSessionStore
from gway.security.oauth import OAuthAuthenticationError, OAuthRegistry
from gway.security.scopes import ScopeRegistry
from gway.security.tokens import TokenRegistry


def _account(tmp_path):
    path = tmp_path / "security.sqlite"
    scopes = ScopeRegistry(path)
    tokens = TokenRegistry(path)
    oauth = OAuthRegistry(path)
    sessions = RemoteSessionStore(lifetime_seconds=300)
    account = RemoteAccountApplication(
        oauth=oauth,
        tokens=tokens,
        sessions=sessions,
    )
    return scopes, tokens, oauth, account


def test_connect_authenticates_bearer_once_and_rotates_browser_session(tmp_path):
    scopes, tokens, oauth, account = _account(tmp_path)
    scopes.create("logs")
    issued = tokens.create("operator", scopes={"logs"})
    session = account.new_session()
    old_id = session.id
    old_csrf = session.csrf

    link = account.connect(
        session,
        csrf=old_csrf,
        bearer=issued.bearer,
    )

    assert link.token_name == "operator"
    assert session.link_name == link.name
    assert session.id != old_id
    assert session.csrf != old_csrf
    assert account.sessions.get(old_id) is None
    assert account.sessions.get(session.id) is session

    with sqlite3.connect(oauth.path) as connection:
        dump = "\n".join(connection.iterdump())
    assert issued.bearer not in dump
    assert not hasattr(session, "bearer")


def test_invalid_bearer_and_csrf_never_create_link(tmp_path):
    scopes, tokens, oauth, account = _account(tmp_path)
    scopes.create("logs")
    issued = tokens.create("operator", scopes={"logs"})
    session = account.new_session()

    with pytest.raises(PermissionError, match="CSRF"):
        account.connect(session, csrf="wrong", bearer=issued.bearer)

    with pytest.raises(PermissionError, match="Invalid bearer"):
        account.connect(session, csrf=session.csrf, bearer="gwt_missing_wrong")

    assert session.link_name is None
    with sqlite3.connect(oauth.path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM oauth_links").fetchone()[0] == 0


def test_consent_displays_live_scope_operations_and_creates_constrained_grant(tmp_path):
    scopes, tokens, oauth, account = _account(tmp_path)
    scopes.replace(
        "chatgpt-logs",
        operations={"log.sources", "log.read"},
        environment=(),
    )
    issued = tokens.create("operator", scopes={"chatgpt-logs"})
    session = account.new_session()
    account.connect(session, csrf=session.csrf, bearer=issued.bearer)
    account.stage_consent(
        session,
        "https://chatgpt.com/client.json",
        {"chatgpt-logs"},
    )

    scopes.replace(
        "chatgpt-logs",
        operations={"log.sources", "log.read", "log.tail"},
        environment=(),
    )
    details = account.consent_details(session)

    assert details["scopes"] == frozenset({"chatgpt-logs"})
    assert details["operations"] == frozenset(
        {"log.sources", "log.read", "log.tail"}
    )
    assert details["environment"] == frozenset()

    grant = account.decide_consent(
        session,
        csrf=session.csrf,
        decision="approve",
    )

    assert grant.client_id == "https://chatgpt.com/client.json"
    assert grant.scopes == frozenset({"chatgpt-logs"})
    assert session.approved_grant_id == grant.id
    assert session.pending_client_id is None
    assert session.pending_scopes == frozenset()


def test_consent_revalidates_scope_binding_before_approval(tmp_path):
    scopes, tokens, _, account = _account(tmp_path)
    scopes.create("logs")
    issued = tokens.create("operator", scopes={"logs"})
    session = account.new_session()
    account.connect(session, csrf=session.csrf, bearer=issued.bearer)
    account.stage_consent(session, "client", {"logs"})

    tokens.unbind("operator", "logs")

    with pytest.raises(PermissionError, match="not available"):
        account.consent_details(session)


def test_denied_consent_creates_no_grant(tmp_path):
    scopes, tokens, oauth, account = _account(tmp_path)
    scopes.create("logs")
    issued = tokens.create("operator", scopes={"logs"})
    session = account.new_session()
    account.connect(session, csrf=session.csrf, bearer=issued.bearer)
    account.stage_consent(session, "client", {"logs"})

    assert account.decide_consent(
        session,
        csrf=session.csrf,
        decision="deny",
    ) is None

    with sqlite3.connect(oauth.path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM oauth_grants").fetchone()[0] == 0


def test_revoke_connection_invalidates_existing_grant(tmp_path):
    scopes, tokens, oauth, account = _account(tmp_path)
    scopes.create("logs")
    issued = tokens.create("operator", scopes={"logs"})
    session = account.new_session()
    account.connect(session, csrf=session.csrf, bearer=issued.bearer)
    account.stage_consent(session, "client", {"logs"})
    grant = account.decide_consent(
        session,
        csrf=session.csrf,
        decision="approve",
    )
    csrf = session.csrf

    assert account.revoke_connection(session, csrf=csrf) is True
    assert session.link_name is None

    with pytest.raises(OAuthAuthenticationError):
        oauth.issue_tokens(grant.id)



def test_permission_summary_limits_preview_and_counts_remaining_operations(tmp_path):
    scopes, _, _, account = _account(tmp_path)
    operations = {f"op.{index}" for index in range(8)}
    scopes.replace("large", operations=operations, environment={"SITE", "ZONE"})

    summary = account.permission_summary({"large"})
    item = summary["scopes"][0]

    assert item["operation_count"] == 8
    assert len(item["operations_preview"]) == 6
    assert item["remaining_operations"] == 2
    assert item["environment_count"] == 2
    assert item["environment"] == ("SITE", "ZONE")


def test_permission_summary_deduplicates_overlapping_effective_access(tmp_path):
    scopes, _, _, account = _account(tmp_path)
    scopes.replace("alpha", operations={"log.read", "log.tail"}, environment={"SITE"})
    scopes.replace("beta", operations={"log.tail", "log.search"}, environment={"SITE", "ZONE"})

    effective = account.permission_summary({"alpha", "beta"})["effective"]

    assert effective["operation_count"] == 3
    assert [item["operations_preview"] for item in account.permission_summary({"alpha", "beta"})["scopes"]] == [
        ("log.read", "log.tail"),
        ("log.search", "log.tail"),
    ]
    assert effective["environment_count"] == 2
    assert effective["environment"] == ("SITE", "ZONE")


def test_permission_summary_uses_operation_metadata_for_mutation_classification(tmp_path):
    scopes, tokens, oauth, _ = _account(tmp_path)
    scopes.replace("mixed", operations={"log.read", "service.restart"}, environment=())

    class Operation:
        def __init__(self, mutates):
            self.mutates = mutates

    operations = {
        "log.read": Operation(False),
        "service.restart": Operation(True),
    }
    account = RemoteAccountApplication(
        oauth=oauth,
        tokens=tokens,
        sessions=RemoteSessionStore(lifetime_seconds=300),
        operation_resolver=operations.get,
    )

    summary = account.permission_summary({"mixed"})

    assert summary["scopes"][0]["mutation_capable"] is True
    assert summary["effective"]["mutation_capable"] is True


def test_permission_summary_treats_unclassified_operation_as_mutation_capable(tmp_path):
    scopes, tokens, oauth, _ = _account(tmp_path)
    scopes.replace("unknown", operations={"plugin.unknown"}, environment=())
    account = RemoteAccountApplication(
        oauth=oauth,
        tokens=tokens,
        sessions=RemoteSessionStore(lifetime_seconds=300),
        operation_resolver=lambda name: None,
    )

    summary = account.permission_summary({"unknown"})

    assert summary["effective"]["mutation_capable"] is True


def test_permission_summary_applies_preview_limit_per_scope(tmp_path):
    scopes, _, _, account = _account(tmp_path)
    scopes.replace(
        "alpha",
        operations={f"alpha.{index}" for index in range(8)},
        environment=(),
    )
    scopes.replace(
        "beta",
        operations={f"beta.{index}" for index in range(7)},
        environment=(),
    )

    summary = account.permission_summary({"alpha", "beta"})
    by_name = {item["name"]: item for item in summary["scopes"]}

    assert len(by_name["alpha"]["operations_preview"]) == 6
    assert by_name["alpha"]["remaining_operations"] == 2
    assert len(by_name["beta"]["operations_preview"]) == 6
    assert by_name["beta"]["remaining_operations"] == 1
    assert all(name.startswith("alpha.") for name in by_name["alpha"]["operations_preview"])
    assert all(name.startswith("beta.") for name in by_name["beta"]["operations_preview"])


def test_approval_grants_current_full_bearer_scope_set(tmp_path):
    scopes, tokens, oauth, account = _account(tmp_path)
    scopes.create("read")
    scopes.create("write")
    scopes.create("admin")
    issued = tokens.create("operator", scopes={"read", "write", "admin"})
    session = account.new_session()

    account.connect(session, csrf=session.csrf, bearer=issued.bearer)
    account.stage_consent(session, "client", {"read"})
    grant = account.decide_consent(
        session,
        csrf=session.csrf,
        decision="approve",
    )

    assert grant.scopes == frozenset({"read", "write", "admin"})
    assert oauth.get_grant(grant.id).scopes == frozenset({"read", "write", "admin"})


def test_approval_revalidates_current_bearer_scope_set(tmp_path):
    scopes, tokens, _, account = _account(tmp_path)
    scopes.create("read")
    scopes.create("write")
    issued = tokens.create("operator", scopes={"read", "write"})
    session = account.new_session()

    account.connect(session, csrf=session.csrf, bearer=issued.bearer)
    account.stage_consent(session, "client", {"read"})
    tokens.unbind("operator", "write")

    grant = account.decide_consent(
        session,
        csrf=session.csrf,
        decision="approve",
    )

    assert grant.scopes == frozenset({"read"})


def test_refresh_preserves_bearer_derived_grant_scope_set(tmp_path):
    scopes, tokens, oauth, account = _account(tmp_path)
    scopes.replace("read", operations={"log.read"})
    scopes.replace("write", operations={"service.restart"})
    issued = tokens.create("operator", scopes={"read", "write"})
    session = account.new_session()

    account.connect(session, csrf=session.csrf, bearer=issued.bearer)
    account.stage_consent(session, "client", {"read"})
    grant = account.decide_consent(
        session,
        csrf=session.csrf,
        decision="approve",
    )
    issued_oauth = oauth.issue_tokens(grant.id)
    refreshed = oauth.rotate_refresh(issued_oauth.refresh_token)

    assert issued_oauth.grant.scopes == frozenset({"read", "write"})
    assert refreshed.grant.scopes == frozenset({"read", "write"})
    assert oauth.authenticate_access(refreshed.access_token).grant.scopes == frozenset(
        {"read", "write"}
    )


def test_scope_policy_changes_affect_effective_authority_without_broadening_grant(tmp_path):
    scopes, tokens, oauth, account = _account(tmp_path)
    scopes.replace("read", operations={"log.read"})
    scopes.replace("write", operations={"service.restart"})
    issued = tokens.create("operator", scopes={"read", "write"})
    session = account.new_session()

    account.connect(session, csrf=session.csrf, bearer=issued.bearer)
    account.stage_consent(session, "client", {"read"})
    grant = account.decide_consent(
        session,
        csrf=session.csrf,
        decision="approve",
    )
    issued_oauth = oauth.issue_tokens(grant.id)

    scopes.replace("read", operations={"log.read", "log.tail"})
    refreshed = oauth.rotate_refresh(issued_oauth.refresh_token)
    authenticated = oauth.authenticate_access(refreshed.access_token)

    assert authenticated.grant.scopes == frozenset({"read", "write"})
    assert authenticated.authority.operations == frozenset(
        {"log.read", "log.tail", "service.restart"}
    )
