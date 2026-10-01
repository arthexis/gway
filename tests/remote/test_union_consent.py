from gway.remote.account import RemoteAccountApplication
from gway.remote.metadata import RemoteOAuthMetadata
from gway.remote.oauth import RemoteOAuthProtocol
from gway.remote.session import RemoteSessionStore
from gway.security.oauth import OAuthRegistry
from gway.security.scopes import ScopeRegistry
from gway.security.tokens import TokenRegistry


def _operation(*, mutates=False):
    def operation():
        return None

    operation.mutates = mutates
    return operation


def _account(tmp_path):
    path = tmp_path / "security.sqlite"
    scopes = ScopeRegistry(path)
    scopes.replace("logs-read", operations={"log.read"})
    scopes.replace(
        "odoo-read",
        operations={"odoo.sales.list"},
        semantic_terms={"odoo", "read"},
    )
    scopes.replace(
        "cards-read",
        operations={"cards.list"},
        semantic_terms={"cards", "read"},
    )
    scopes.replace(
        "odoo-cards-detail-read",
        operations={"odoo.cards.detail"},
        semantic_terms={"odoo", "cards", "detail", "read"},
    )
    tokens = TokenRegistry(path)
    issued = tokens.create(
        "operator",
        scopes={"logs-read"},
        union_scopes={("read",)},
    )
    oauth = OAuthRegistry(path)
    operations = {
        "log.read": _operation(),
        "odoo.sales.list": _operation(),
        "cards.list": _operation(),
        "odoo.cards.detail": _operation(),
    }
    account = RemoteAccountApplication(
        oauth=oauth,
        tokens=tokens,
        sessions=RemoteSessionStore(),
        operation_resolver=operations.get,
    )
    session = account.new_session()
    account.connect(session, csrf=session.csrf, bearer=issued.bearer)
    return account, session


def test_existing_consent_ui_renders_and_persists_exact_and_union_authority(tmp_path):
    account, session = _account(tmp_path)
    account.stage_consent(
        session,
        "client",
        "logs-read",
        union_scopes="cards,read",
        resource="https://remote.example/mcp",
    )

    page = account.consent_page(session)

    assert "Exact scopes" in page
    assert "logs-read" in page
    assert "Union scopes" in page
    assert "cards + read" in page
    assert "cards-read" in page
    assert "Future scopes matching all of these terms may also be included" in page
    assert "full effective scope set associated with the linked bearer" not in page

    grant = account.decide_consent(
        session,
        csrf=session.csrf,
        decision="approve",
    )

    assert grant.scopes == frozenset({"logs-read"})
    assert grant.union_scopes == frozenset({("cards", "read")})
    assert session.pending_scopes == frozenset()
    assert session.pending_union_scopes == frozenset()


def test_union_consent_uses_and_representation_without_broadening(tmp_path):
    account, session = _account(tmp_path)
    account.stage_consent(
        session,
        "client",
        (),
        union_scopes="odoo,cards,read",
    )

    details = account.consent_details(session)
    union = details["union_summary"][0]

    assert union["exact_scopes"] == ()
    assert union["conjunction"] == ("cards-read", "odoo-read")
    assert union["matched_scopes"] == ("odoo-cards-detail-read",)
    assert details["operations"] == frozenset({"odoo.cards.detail"})
    page = account.consent_page(session)
    assert "cards-read AND odoo-read" in page


def test_oauth_authorization_accepts_union_scope_without_forcing_default_exact_scope(
    tmp_path,
):
    account, session = _account(tmp_path)
    account.oauth.create_client(
        "client",
        redirect_uris={"https://client.example/callback"},
    )
    metadata = RemoteOAuthMetadata(
        "https://remote.example",
        "https://remote.example/mcp",
        ("full-access",),
    )
    protocol = RemoteOAuthProtocol(metadata, account, default_scope="full-access")

    protocol.stage_authorization(
        session,
        {
            "response_type": "code",
            "client_id": "client",
            "redirect_uri": "https://client.example/callback",
            "resource": metadata.resource,
            "code_challenge": "a" * 43,
            "code_challenge_method": "S256",
            "union_scope": "cards,read;odoo,cards,read",
        },
    )

    assert session.pending_scopes == frozenset()
    assert session.pending_union_scopes == frozenset(
        {("cards", "read"), ("cards", "odoo", "read")}
    )
