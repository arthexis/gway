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
    assert session.available_scopes == frozenset({"logs"})
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
    assert details["available_scopes"] == frozenset({"chatgpt-logs"})
    assert details["requested_scopes"] == frozenset({"chatgpt-logs"})
    assert details["operations"] == frozenset(
        {"log.sources", "log.read", "log.tail"}
    )
    assert details["environment"] == frozenset()

    grant = account.decide_consent(
        session,
        csrf=session.csrf,
        decision="approve",
        scopes={"chatgpt-logs"},
    )

    assert grant.client_id == "https://chatgpt.com/client.json"
    assert grant.scopes == frozenset({"chatgpt-logs"})
    assert session.approved_grant_id == grant.id
    assert session.pending_client_id is None
    assert session.requested_scopes == frozenset()
    assert session.selected_scopes == frozenset()


def test_consent_revalidates_scope_binding_before_approval(tmp_path):
    scopes, tokens, _, account = _account(tmp_path)
    scopes.create("logs")
    issued = tokens.create("operator", scopes={"logs"})
    session = account.new_session()
    account.connect(session, csrf=session.csrf, bearer=issued.bearer)
    account.stage_consent(session, "client", {"logs"})

    tokens.unbind("operator", "logs")

    with pytest.raises(PermissionError, match="no longer available"):
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
        scopes={"logs"},
    )
    csrf = session.csrf

    assert account.revoke_connection(session, csrf=csrf) is True
    assert session.link_name is None

    with pytest.raises(OAuthAuthenticationError):
        oauth.issue_tokens(grant.id)


def test_consent_state_distinguishes_available_requested_and_selected_scopes(tmp_path):
    scopes, tokens, _, account = _account(tmp_path)
    scopes.create("read")
    scopes.create("write")
    issued = tokens.create("operator", scopes={"read", "write"})
    session = account.new_session()

    account.connect(session, csrf=session.csrf, bearer=issued.bearer)
    account.stage_consent(session, "client", {"read"})

    assert session.available_scopes == frozenset({"read", "write"})
    assert session.requested_scopes == frozenset({"read"})
    assert session.selected_scopes == frozenset({"read"})


def test_consent_rejects_selection_outside_requested_scope_set(tmp_path):
    scopes, tokens, _, account = _account(tmp_path)
    scopes.create("read")
    scopes.create("write")
    issued = tokens.create("operator", scopes={"read", "write"})
    session = account.new_session()

    account.connect(session, csrf=session.csrf, bearer=issued.bearer)
    account.stage_consent(session, "client", {"read"})
    session.selected_scopes = frozenset({"write"})

    with pytest.raises(PermissionError, match="not requested"):
        account.consent_details(session)


def test_consent_refreshes_available_scopes_from_current_token_binding(tmp_path):
    scopes, tokens, _, account = _account(tmp_path)
    scopes.create("read")
    scopes.create("write")
    issued = tokens.create("operator", scopes={"read", "write"})
    session = account.new_session()

    account.connect(session, csrf=session.csrf, bearer=issued.bearer)
    account.stage_consent(session, "client", {"read"})
    tokens.unbind("operator", "write")

    details = account.consent_details(session)

    assert session.available_scopes == frozenset({"read"})
    assert details["available_scopes"] == frozenset({"read"})


def test_oauth_request_broader_than_bearer_is_constrained_to_intersection(tmp_path):
    scopes, tokens, _, account = _account(tmp_path)
    scopes.create("read")
    scopes.create("write")
    issued = tokens.create("operator", scopes={"read"})
    session = account.new_session()

    account.stage_consent(session, "client", {"read", "write"})
    account.connect(session, csrf=session.csrf, bearer=issued.bearer)

    details = account.consent_details(session)

    assert session.available_scopes == frozenset({"read"})
    assert session.requested_scopes == frozenset({"read", "write"})
    assert session.selected_scopes == frozenset({"read"})
    assert details["scopes"] == frozenset({"read"})


def test_scope_selection_accepts_subset_of_requested_and_available_scopes(tmp_path):
    scopes, tokens, _, account = _account(tmp_path)
    scopes.create("read")
    scopes.create("write")
    issued = tokens.create("operator", scopes={"read", "write"})
    session = account.new_session()

    account.connect(session, csrf=session.csrf, bearer=issued.bearer)
    account.stage_consent(session, "client", {"read", "write"})

    selected = account.select_scopes(session, {"read"})

    assert selected == frozenset({"read"})
    assert session.selected_scopes == frozenset({"read"})


def test_scope_selection_rejects_empty_and_non_delegable_values(tmp_path):
    scopes, tokens, _, account = _account(tmp_path)
    scopes.create("read")
    scopes.create("write")
    issued = tokens.create("operator", scopes={"read"})
    session = account.new_session()

    account.connect(session, csrf=session.csrf, bearer=issued.bearer)
    account.stage_consent(session, "client", {"read", "write"})

    with pytest.raises(ValueError, match="At least one scope"):
        account.select_scopes(session, set())

    with pytest.raises(PermissionError, match="not delegable"):
        account.select_scopes(session, {"write"})


def test_scope_selection_revalidates_live_bearer_before_accepting_post(tmp_path):
    scopes, tokens, _, account = _account(tmp_path)
    scopes.create("read")
    scopes.create("write")
    issued = tokens.create("operator", scopes={"read", "write"})
    session = account.new_session()

    account.connect(session, csrf=session.csrf, bearer=issued.bearer)
    account.stage_consent(session, "client", {"read", "write"})
    tokens.unbind("operator", "write")

    with pytest.raises(PermissionError, match="not delegable"):
        account.select_scopes(session, {"write"})


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


def test_approval_persists_exact_selected_scope_subset(tmp_path):
    scopes, tokens, oauth, account = _account(tmp_path)
    scopes.create("read")
    scopes.create("write")
    scopes.create("admin")
    issued = tokens.create("operator", scopes={"read", "write", "admin"})
    session = account.new_session()

    account.connect(session, csrf=session.csrf, bearer=issued.bearer)
    account.stage_consent(session, "client", {"read", "write"})
    grant = account.decide_consent(
        session,
        csrf=session.csrf,
        decision="approve",
        scopes={"read"},
    )

    assert grant.scopes == frozenset({"read"})
    assert oauth.get_grant(grant.id).scopes == frozenset({"read"})


def test_approval_persists_exact_multi_scope_selection(tmp_path):
    scopes, tokens, oauth, account = _account(tmp_path)
    scopes.create("read")
    scopes.create("write")
    scopes.create("admin")
    issued = tokens.create("operator", scopes={"read", "write", "admin"})
    session = account.new_session()

    account.connect(session, csrf=session.csrf, bearer=issued.bearer)
    account.stage_consent(session, "client", {"read", "write", "admin"})
    grant = account.decide_consent(
        session,
        csrf=session.csrf,
        decision="approve",
        scopes={"read", "write"},
    )

    assert grant.scopes == frozenset({"read", "write"})
    assert oauth.get_grant(grant.id).scopes == frozenset({"read", "write"})


def test_refresh_preserves_named_grant_scope_subset(tmp_path):
    scopes, tokens, oauth, account = _account(tmp_path)
    scopes.replace("read", operations={"log.read"})
    scopes.replace("write", operations={"service.restart"})
    issued = tokens.create("operator", scopes={"read", "write"})
    session = account.new_session()

    account.connect(session, csrf=session.csrf, bearer=issued.bearer)
    account.stage_consent(session, "client", {"read", "write"})
    grant = account.decide_consent(
        session,
        csrf=session.csrf,
        decision="approve",
        scopes={"read"},
    )
    issued_oauth = oauth.issue_tokens(grant.id)
    refreshed = oauth.rotate_refresh(issued_oauth.refresh_token)

    assert issued_oauth.grant.scopes == frozenset({"read"})
    assert refreshed.grant.scopes == frozenset({"read"})
    assert oauth.authenticate_access(refreshed.access_token).grant.scopes == frozenset(
        {"read"}
    )


def test_scope_policy_changes_affect_effective_authority_without_broadening_grant(tmp_path):
    scopes, tokens, oauth, account = _account(tmp_path)
    scopes.replace("read", operations={"log.read"})
    scopes.replace("write", operations={"service.restart"})
    issued = tokens.create("operator", scopes={"read", "write"})
    session = account.new_session()

    account.connect(session, csrf=session.csrf, bearer=issued.bearer)
    account.stage_consent(session, "client", {"read", "write"})
    grant = account.decide_consent(
        session,
        csrf=session.csrf,
        decision="approve",
        scopes={"read"},
    )
    issued_oauth = oauth.issue_tokens(grant.id)

    scopes.replace("read", operations={"log.read", "log.tail"})
    refreshed = oauth.rotate_refresh(issued_oauth.refresh_token)
    authenticated = oauth.authenticate_access(refreshed.access_token)

    assert authenticated.grant.scopes == frozenset({"read"})
    assert authenticated.authority.operations == frozenset({"log.read", "log.tail"})


def test_browser_session_changes_after_approval_do_not_mutate_stored_grant(tmp_path):
    scopes, tokens, oauth, account = _account(tmp_path)
    scopes.create("read")
    scopes.create("write")
    issued = tokens.create("operator", scopes={"read", "write"})
    session = account.new_session()

    account.connect(session, csrf=session.csrf, bearer=issued.bearer)
    account.stage_consent(session, "client", {"read", "write"})
    grant = account.decide_consent(
        session,
        csrf=session.csrf,
        decision="approve",
        scopes={"read"},
    )

    session.selected_scopes = frozenset({"write"})
    session.requested_scopes = frozenset({"write"})
    session.available_scopes = frozenset({"write"})

    assert oauth.get_grant(grant.id).scopes == frozenset({"read"})
