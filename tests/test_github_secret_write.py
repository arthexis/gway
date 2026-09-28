import base64
from types import SimpleNamespace

import pytest

from gway.githubops import Controller


class FakeClient:
    def __init__(self):
        self.calls = []

    def request(self, method, path, *, params=None, json=None, headers=None):
        self.calls.append((method, path, json))
        if path.endswith("/actions/secrets/public-key"):
            return SimpleNamespace(data={"key_id": "kid", "key": "public-key"})
        return SimpleNamespace(data=None)


def test_secret_key_is_read_only_metadata():
    client = FakeClient()
    target = Controller(None, client=client)

    assert target.secret_key("arthexis/gway") == {
        "key_id": "kid",
        "key": "public-key",
    }


def test_set_secret_sends_only_encrypted_value(monkeypatch):
    sentinel = "PLAINTEXT-SECRET-SENTINEL"
    encrypted = base64.b64encode(b"sealed-ciphertext").decode("ascii")
    client = FakeClient()
    target = Controller(None, client=client)
    monkeypatch.setattr(target, "_encrypt_secret", lambda key, value: encrypted)

    result = target.set_secret("arthexis/gway", "TOKEN", sentinel)

    assert result == {"name": "TOKEN", "updated": True}
    method, path, payload = client.calls[-1]
    assert method == "PUT"
    assert path == "/repos/arthexis/gway/actions/secrets/TOKEN"
    assert payload == {"encrypted_value": encrypted, "key_id": "kid"}
    assert sentinel not in repr(result)
    assert sentinel not in repr(client.calls)


def test_delete_secret_returns_no_secret_material():
    client = FakeClient()
    target = Controller(None, client=client)

    assert target.delete_secret("arthexis/gway", "TOKEN") == {
        "name": "TOKEN",
        "deleted": True,
    }
    assert client.calls[-1] == (
        "DELETE",
        "/repos/arthexis/gway/actions/secrets/TOKEN",
        None,
    )


def test_secret_write_requires_pynacl_when_unavailable(monkeypatch):
    import builtins

    original = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name == "nacl":
            raise ImportError("blocked")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)

    with pytest.raises(RuntimeError, match="require PyNaCl"):
        Controller._encrypt_secret("unused", "secret")


def test_secret_operations_have_split_read_write_authorization(gateway):
    read = gateway.ops.resolve("github.secret_key")
    assert read is not None
    assert read.mutates is False
    assert {"github", "source", "read"} <= set(read.__gway_metadata__["topics"])

    for name in {"github.set_secret", "github.delete_secret"}:
        operation = gateway.ops.resolve(name)
        assert operation is not None
        assert operation.mutates is True
        topics = set(operation.__gway_metadata__["topics"])
        assert {"github", "source", "write"} <= topics
        assert "read" not in topics
