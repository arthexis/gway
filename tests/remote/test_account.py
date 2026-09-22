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
    )
    csrf = session.csrf

    assert account.revoke_connection(session, csrf=csrf) is True
    assert session.link_name is None

    with pytest.raises(OAuthAuthenticationError):
        oauth.issue_tokens(grant.id)
