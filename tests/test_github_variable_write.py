from types import SimpleNamespace

from gway.github import GitHubError
from gway.githubops import Controller


class FakeClient:
    def __init__(self, exists=True):
        self.exists = exists
        self.calls = []

    def request(self, method, path, *, params=None, json=None, headers=None):
        self.calls.append((method, path, json))
        if method == "GET" and "/actions/variables/" in path and not self.exists:
            raise GitHubError(404, "Not Found")
        return SimpleNamespace(data=None)


def test_set_variable_creates_when_missing():
    client = FakeClient(exists=False)
    target = Controller(None, client=client)

    result = target.set_variable("arthexis/gway", "DEPLOY_ENV", "production")

    assert result == {
        "name": "DEPLOY_ENV",
        "value": "production",
        "created": True,
    }
    assert client.calls[-1] == (
        "POST",
        "/repos/arthexis/gway/actions/variables",
        {"name": "DEPLOY_ENV", "value": "production"},
    )


def test_set_variable_updates_when_present():
    client = FakeClient(exists=True)
    target = Controller(None, client=client)

    result = target.set_variable("arthexis/gway", "DEPLOY_ENV", "staging")

    assert result["created"] is False
    assert client.calls[-1] == (
        "PATCH",
        "/repos/arthexis/gway/actions/variables/DEPLOY_ENV",
        {"name": "DEPLOY_ENV", "value": "staging"},
    )


def test_delete_variable_uses_delete():
    client = FakeClient()
    target = Controller(None, client=client)

    assert target.delete_variable("arthexis/gway", "DEPLOY_ENV") == {
        "name": "DEPLOY_ENV",
        "deleted": True,
    }
    assert client.calls[-1] == (
        "DELETE",
        "/repos/arthexis/gway/actions/variables/DEPLOY_ENV",
        None,
    )


def test_variable_mutations_are_source_write(gateway):
    for name in {"github.set_variable", "github.delete_variable"}:
        operation = gateway.ops.resolve(name)
        assert operation is not None
        assert operation.mutates is True
        topics = set(operation.__gway_metadata__["topics"])
        assert {"github", "source", "write"} <= topics
        assert "read" not in topics
