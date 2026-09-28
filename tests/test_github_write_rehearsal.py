from types import SimpleNamespace

import pytest

from gway.authorization import AuthorizationError
from gway.githubops import Controller


class RehearsalClient:
    def __init__(self):
        self.variables = {}
        self.secrets = set()
        self.calls = []

    def request(self, method, path, *, params=None, json=None, headers=None):
        self.calls.append((method, path, json))
        if path.endswith("/actions/secrets/public-key"):
            return SimpleNamespace(data={"key_id": "kid", "key": "public"})
        if "/actions/variables/" in path:
            name = path.rsplit("/", 1)[-1]
            if method == "GET":
                if name not in self.variables:
                    from gway.github import GitHubError
                    raise GitHubError(404, "missing")
                return SimpleNamespace(
                    data={"name": name, "value": self.variables[name]}
                )
            if method == "PATCH":
                self.variables[name] = json["value"]
            elif method == "DELETE":
                self.variables.pop(name, None)
            return SimpleNamespace(data=None)
        if path.endswith("/actions/variables"):
            if method == "GET":
                return SimpleNamespace(
                    data={
                        "variables": [
                            {"name": name, "value": value}
                            for name, value in self.variables.items()
                        ]
                    }
                )
            self.variables[json["name"]] = json["value"]
            return SimpleNamespace(data=None)
        if "/actions/secrets/" in path:
            name = path.rsplit("/", 1)[-1]
            if method == "PUT":
                self.secrets.add(name)
            elif method == "DELETE":
                self.secrets.discard(name)
            return SimpleNamespace(data=None)
        if path.endswith("/actions/secrets"):
            return SimpleNamespace(
                data={
                    "secrets": [
                        {"name": name, "created_at": "now", "updated_at": "now"}
                        for name in sorted(self.secrets)
                    ]
                }
            )
        raise AssertionError((method, path))


def test_read_authority_cannot_invoke_write_operation(gateway):
    with gateway.authorized(operations={"github.variable"}):
        with pytest.raises(AuthorizationError, match="github.set_variable"):
            gateway("github set variable repo/name ENV production")


def test_write_authority_can_invoke_registered_write(monkeypatch, gateway):
    client = RehearsalClient()
    gateway._github_controller._client = client

    with gateway.authorized(operations={"github.set_variable"}):
        result = gateway("github set variable repo/name ENV production")

    assert result["name"] == "ENV"
    assert client.variables == {"ENV": "production"}


def test_configuration_write_lifecycle_never_exposes_plaintext_secret(monkeypatch):
    sentinel = "PLAINTEXT-SECRET-SENTINEL"
    client = RehearsalClient()
    target = Controller(None, client=client)
    monkeypatch.setattr(target, "_encrypt_secret", lambda *args: "sealed-value")

    assert target.variables("repo/name") == []
    target.set_variable("repo/name", "ENV", "production")
    assert target.variable("repo/name", "ENV")["value"] == "production"

    secret_result = target.set_secret("repo/name", "TOKEN", sentinel)
    secret_metadata = target.secrets("repo/name")
    target.delete_secret("repo/name", "TOKEN")
    target.delete_variable("repo/name", "ENV")

    observable = repr(
        {
            "result": secret_result,
            "metadata": secret_metadata,
            "calls": client.calls,
        }
    )
    assert sentinel not in observable
    assert secret_metadata == [
        {"name": "TOKEN", "created_at": "now", "updated_at": "now"}
    ]
    assert client.variables == {}
    assert client.secrets == set()
