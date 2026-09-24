from io import BytesIO
from types import SimpleNamespace

from gway.recipe import companion
from gway.security.scopes import EffectiveScope
from gway.security.tokens import AuthenticatedToken, Token


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
    }
    assert captured["path"] == gateway.security_path
