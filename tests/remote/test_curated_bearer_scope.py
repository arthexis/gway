from types import SimpleNamespace

from gway.remote.account import RemoteAccountApplication
from gway.remote.session import RemoteSessionStore
from gway.security.oauth import OAuthRegistry
from gway.security.scopes import ScopeRegistry
from gway.security.tokens import TokenRegistry


RESOURCE = "https://remote.example.test/mcp"


def _account(tmp_path, operations):
    path = tmp_path / "security.sqlite"
    scopes = ScopeRegistry(path)
    tokens = TokenRegistry(path)
    oauth = OAuthRegistry(path)
    account = RemoteAccountApplication(
        oauth=oauth,
        tokens=tokens,
        sessions=RemoteSessionStore(lifetime_seconds=300),
        operation_resolver=lambda name: operations.get(name),
    )
    return scopes, tokens, oauth, account


def test_unspecified_oauth_scope_inherits_linked_bearer_scopes(tmp_path):
    operations = {
        "log.read": SimpleNamespace(mutates=False),
        "github.drive": SimpleNamespace(mutates=True),
    }
    scopes, tokens, _oauth, account = _account(tmp_path, operations)
    scopes.replace("operator-read", operations={"log.read"})
    scopes.replace("operator-write", operations={"github.drive"})
    issued = tokens.create(
        "operator",
        scopes={"operator-read", "operator-write"},
    )

    session = account.new_session()
    account.stage_consent(
        session,
        "chatgpt",
        resource=RESOURCE,
    )
    assert session.pending_scopes == frozenset()

    account.connect(session, csrf=session.csrf, bearer=issued.bearer)
    assert session.pending_scopes == frozenset({"operator-read", "operator-write"})

    details = account.consent_details(session)
    assert details["scopes"] == frozenset({"operator-read", "operator-write"})
    assert details["operations"] == frozenset({"log.read", "github.drive"})
    assert details["permission_summary"]["effective"]["mutation_capable"] is True

    grant = account.decide_consent(session, csrf=session.csrf, decision="approve")
    assert grant.scopes == frozenset({"operator-read", "operator-write"})


def test_explicit_narrow_scope_does_not_expand_to_full_bearer(tmp_path):
    operations = {
        "log.read": SimpleNamespace(mutates=False),
        "github.drive": SimpleNamespace(mutates=True),
    }
    scopes, tokens, _oauth, account = _account(tmp_path, operations)
    scopes.replace("operator-read", operations={"log.read"})
    scopes.replace("operator-write", operations={"github.drive"})
    issued = tokens.create(
        "operator",
        scopes={"operator-read", "operator-write"},
    )

    session = account.new_session()
    account.stage_consent(
        session,
        "chatgpt",
        scopes={"operator-read"},
        resource=RESOURCE,
    )
    account.connect(session, csrf=session.csrf, bearer=issued.bearer)

    details = account.consent_details(session)
    assert details["scopes"] == frozenset({"operator-read"})
    assert details["operations"] == frozenset({"log.read"})
    assert details["permission_summary"]["effective"]["mutation_capable"] is False


def test_scope_mutation_status_is_derived_from_member_operations(tmp_path):
    operations = {
        "known.read": SimpleNamespace(mutates=False),
        "known.write": SimpleNamespace(mutates=True),
    }
    scopes, _tokens, _oauth, account = _account(tmp_path, operations)
    scopes.replace("read-only", operations={"known.read"})
    scopes.replace("mixed", operations={"known.read", "known.write"})
    scopes.replace("unknown", operations={"missing.operation"})

    assert account.permission_summary({"read-only"})["effective"]["mutation_capable"] is False
    assert account.permission_summary({"mixed"})["effective"]["mutation_capable"] is True
    assert account.permission_summary({"unknown"})["effective"]["mutation_capable"] is True
