import pytest

from gway.github import GitHubError
from gway.githubops import Controller


def test_variable_create_race_converges_with_update(github_client):
    client = github_client([
        GitHubError(404, "missing"),
        GitHubError(422, "already exists"),
        None,
    ])
    result = Controller(None, client=client).set_variable(
        "arthexis/gway", "ENV", "production"
    )

    assert result["created"] is False
    assert [call["method"] for call in client.calls] == ["GET", "POST", "PATCH"]


def test_variable_delete_race_converges_with_create(github_client):
    client = github_client([None, GitHubError(404, "missing"), None])
    result = Controller(None, client=client).set_variable(
        "arthexis/gway", "ENV", "production"
    )

    assert result["created"] is True
    assert [call["method"] for call in client.calls] == ["GET", "PATCH", "POST"]


@pytest.mark.parametrize("status", [401, 403, 500])
def test_variable_lookup_failures_are_not_swallowed(status, github_client):
    error = GitHubError(status, "failure")
    client = github_client([error])

    with pytest.raises(GitHubError) as captured:
        Controller(None, client=client).set_variable(
            "arthexis/gway", "ENV", "production"
        )

    assert captured.value is error
    assert len(client.calls) == 1


def test_secret_rejects_incomplete_public_key_before_encryption(monkeypatch, github_client):
    client = github_client([{"key_id": "kid"}])
    target = Controller(None, client=client)
    called = []
    monkeypatch.setattr(
        target,
        "_encrypt_secret",
        lambda *args: called.append(args),
    )

    with pytest.raises(ValueError, match="public key response is incomplete"):
        target.set_secret("arthexis/gway", "TOKEN", "secret")

    assert called == []
    assert len(client.calls) == 1


def test_secret_encryption_failure_prevents_mutation(monkeypatch, github_client):
    client = github_client([{"key_id": "kid", "key": "public"}])
    target = Controller(None, client=client)

    def fail(*args):
        raise ValueError("invalid public key")

    monkeypatch.setattr(target, "_encrypt_secret", fail)

    with pytest.raises(ValueError, match="invalid public key"):
        target.set_secret("arthexis/gway", "TOKEN", "secret")

    assert len(client.calls) == 1


def test_secret_github_mutation_failure_propagates(monkeypatch, github_client):
    error = GitHubError(403, "Resource not accessible")
    client = github_client([
        {"key_id": "kid", "key": "public"},
        error,
    ])
    target = Controller(None, client=client)
    monkeypatch.setattr(target, "_encrypt_secret", lambda *args: "encrypted")

    with pytest.raises(GitHubError) as captured:
        target.set_secret("arthexis/gway", "TOKEN", "secret")

    assert captured.value is error
