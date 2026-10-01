from io import BytesIO

from gway.recipe import companion
from gway.security.scopes import EffectiveScope, ScopeRegistry
from gway.security.tokens import AuthenticatedToken, Token, TokenRegistry


def test_companion_bearer_authentication_uses_parent_security_path(
    gateway,
    monkeypatch,
):
    captured = {}

    class Registry:
        def __init__(self, path):
            captured["path"] = path

        def authenticate(self, bearer):
            return AuthenticatedToken(
                Token(
                    name="client",
                    public_id="public",
                    scopes=frozenset({"reader"}),
                    disabled=False,
                    created_at="2026-09-24T00:00:00+00:00",
                ),
                EffectiveScope(
                    operations=frozenset({"log.read"}),
                    environment=frozenset(),
                ),
            )

    monkeypatch.setattr(companion, "TokenRegistry", Registry)

    stream = BytesIO()
    companion._service_parent_request(
        gateway,
        stream,
        {
            "type": "request",
            "id": "1",
            "method": "gateway.authenticate_bearer",
            "params": {
                "bearer": "gwt_public_secret",
                "resource": "https://remote.example.test/mcp",
            },
        },
    )

    stream.seek(0)
    response = companion._read_message(stream)

    assert response["ok"] is True
    assert response["result"] == {
        "kind": "gway",
        "principal": "client",
        "client_id": "gway:client",
        "scopes": ["reader"],
        "mutation_capable": False,
    }
    assert captured["path"] == gateway.security_path



def test_authority_mutation_capability_uses_operation_metadata(gateway):
    def observe(*, mutate=False):
        return mutate

    def restart():
        return True

    gateway.observe = gateway.wrap("observe_status", observe)
    gateway.restart = gateway.wrap("restart_service", restart)

    assert companion._authority_mutation_capable(
        gateway,
        {"observe_status"},
    ) is False
    assert companion._authority_mutation_capable(
        gateway,
        {"restart_service"},
    ) is True
    assert companion._authority_mutation_capable(
        gateway,
        {"missing.operation"},
    ) is True
    assert companion._authority_mutation_capable(
        gateway,
        {"__all__"},
    ) is True


def test_companion_reports_mutation_capability_from_exact_curated_bundle(
    gateway,
    tmp_path,
):
    gateway.security_path = tmp_path / "security.sqlite"

    def observe(*, mutate=False):
        return mutate

    def restart():
        return True

    gateway.observe = gateway.wrap("demo.observe", observe)
    gateway.restart = gateway.wrap("demo.restart", restart)

    scopes = ScopeRegistry(gateway.security_path)
    scopes.replace("observer", operations={"demo.observe"})
    scopes.replace("operator", operations={"demo.restart"})
    tokens = TokenRegistry(gateway.security_path)
    reader = tokens.create("reader", scopes={"observer"})
    writer = tokens.create("writer", scopes={"observer", "operator"})

    def authenticate(bearer, request_id):
        stream = BytesIO()
        companion._service_parent_request(
            gateway,
            stream,
            {
                "type": "request",
                "id": request_id,
                "method": "gateway.authenticate_bearer",
                "params": {"bearer": bearer},
            },
        )
        stream.seek(0)
        return companion._read_message(stream)["result"]

    read_identity = authenticate(reader.bearer, "reader")
    write_identity = authenticate(writer.bearer, "writer")

    assert read_identity["scopes"] == ["observer"]
    assert read_identity["mutation_capable"] is False
    assert write_identity["scopes"] == ["observer", "operator"]
    assert write_identity["mutation_capable"] is True


def test_parent_bridge_parses_leading_globals(gateway):
    stream = BytesIO()
    with gateway.authorized(
        operations={'builtins', 'filter', 'version'}, environment=set(),
    ):
        companion._service_parent_request(
            gateway, stream,
            {
                'type': 'request', 'id': 'globals', 'method': 'gateway.execute',
                'params': {
                    'command': '-j --timed builtins - filter --name version',
                    'mutate': False,
                },
            },
        )
    stream.seek(0)
    response = companion._read_message(stream)
    assert response['ok'] is True
    assert [record['name'] for record in response['result']] == ['version']
    assert gateway.call_timed is False
