import base64

import pytest

from gway.githubops import Controller


def test_secret_key_is_read_only_metadata(github_client):
    client = github_client([{"key_id": "kid", "key": "public-key"}])
    target = Controller(None, client=client)

    assert target.secret_key("arthexis/gway") == {
        "key_id": "kid",
        "key": "public-key",
    }


def test_set_secret_sends_only_encrypted_value(monkeypatch, github_client):
    sentinel = "PLAINTEXT-SECRET-SENTINEL"
    encrypted = base64.b64encode(b"sealed-ciphertext").decode("ascii")
    client = github_client([{"key_id": "kid", "key": "public-key"}])
    target = Controller(None, client=client)
    monkeypatch.setattr(target, "_encrypt_secret", lambda key, value: encrypted)

    result = target.set_secret("arthexis/gway", "TOKEN", sentinel)

    assert result == {"name": "TOKEN", "updated": True}
    call = client.calls[-1]
    assert call["method"] == "PUT"
    assert call["path"] == "/repos/arthexis/gway/actions/secrets/TOKEN"
    assert call["json"] == {"encrypted_value": encrypted, "key_id": "kid"}
    assert sentinel not in repr(result)
    assert sentinel not in repr(client.calls)


def test_delete_secret_returns_no_secret_material(github_client):
    client = github_client()
    target = Controller(None, client=client)

    assert target.delete_secret("arthexis/gway", "TOKEN") == {
        "name": "TOKEN",
        "deleted": True,
    }
    assert client.calls[-1]["method"] == "DELETE"
    assert client.calls[-1]["path"].endswith("/actions/secrets/TOKEN")


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
