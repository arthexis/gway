import base64
from types import SimpleNamespace

import pytest

from gway.authorization import AuthorizationError
from gway.github import GitHubError
from gway.githubops import Controller


WRITE_OPERATIONS = {
    "github.dispatch_workflow",
    "github.dispatch_repository",
    "github.create_release",
    "github.update_release",
    "github.create_ref",
    "github.create_branch",
    "github.delete_ref",
    "github.delete_branch",
    "github.create_file",
    "github.update_file",
    "github.delete_file",
}


class RepositoryMutationClient:
    def __init__(self):
        self.calls = []
        self.refs = {}
        self.files = {}
        self.releases = {}
        self.dispatches = []

    def request(self, method, path, *, params=None, json=None, headers=None):
        self.calls.append((method, path, json))
        if path.endswith("/dispatches") and method == "POST":
            self.dispatches.append((path, dict(json)))
            return SimpleNamespace(data=None)
        if path.endswith("/releases") and method == "POST":
            release = {"id": 1, **json}
            self.releases[1] = release
            return SimpleNamespace(data=dict(release))
        if path.endswith("/releases/1") and method == "PATCH":
            self.releases[1].update(json)
            return SimpleNamespace(data=dict(self.releases[1]))
        if path.endswith("/git/refs") and method == "POST":
            if json["ref"] in self.refs:
                raise GitHubError(422, "Reference already exists")
            self.refs[json["ref"]] = json["sha"]
            return SimpleNamespace(
                data={"ref": json["ref"], "object": {"sha": json["sha"]}}
            )
        if "/git/refs/" in path and method == "DELETE":
            ref = "refs/" + path.split("/git/refs/", 1)[1]
            self.refs.pop(ref, None)
            return SimpleNamespace(data=None)
        if "/contents/" in path:
            file_path = path.split("/contents/", 1)[1]
            if method == "PUT":
                expected = json.get("sha")
                current = self.files.get(file_path)
                if expected is not None and (
                    current is None or expected != current["sha"]
                ):
                    raise GitHubError(409, "File SHA does not match")
                next_sha = f"blob-{len(self.files) + len(self.calls)}"
                self.files[file_path] = {
                    "sha": next_sha,
                    "content": json["content"],
                }
                return SimpleNamespace(data={"content": {"sha": next_sha}})
            if method == "DELETE":
                current = self.files.get(file_path)
                if current is None or json["sha"] != current["sha"]:
                    raise GitHubError(409, "File SHA does not match")
                del self.files[file_path]
                return SimpleNamespace(data={"commit": {"sha": "delete-commit"}})
        raise AssertionError((method, path, json))


@pytest.mark.parametrize("operation", sorted(WRITE_OPERATIONS))
def test_read_authority_rejects_g6_writes(gateway, operation):
    with gateway.authorized(operations={"github.repository", "github.file"}):
        with pytest.raises(AuthorizationError, match=operation):
            gateway.authorization.authorize_operation(operation)


def test_repository_mutation_lifecycle_rehearsal():
    client = RepositoryMutationClient()
    target = Controller(None, client=client)

    target.dispatch_workflow(
        "repo/name", "deploy.yml", "main", inputs={"remote": "true"}
    )
    target.dispatch_repository("repo/name", "refresh", payload={"node": "watchtower"})

    release = target.create_release(
        "repo/name", "v1", target="main", draft=True
    )
    published = target.update_release(
        "repo/name", release["id"], draft=False
    )

    branch = target.create_branch("repo/name", "release/v1", "commit-sha")
    created = target.create_file(
        "repo/name",
        "release.txt",
        "one",
        "Create release marker",
        branch="release/v1",
    )
    updated = target.update_file(
        "repo/name",
        "release.txt",
        "two",
        "Update release marker",
        created["content"]["sha"],
        branch="release/v1",
    )
    target.delete_file(
        "repo/name",
        "release.txt",
        "Remove release marker",
        updated["content"]["sha"],
        branch="release/v1",
    )
    deleted = target.delete_branch("repo/name", "release/v1")

    assert len(client.dispatches) == 2
    assert published["draft"] is False
    assert branch["ref"] == "refs/heads/release/v1"
    assert client.files == {}
    assert deleted["deleted"] is True
    assert client.refs == {}


def test_file_rehearsal_rejects_stale_blob_sha():
    client = RepositoryMutationClient()
    target = Controller(None, client=client)
    created = target.create_file("repo/name", "a.txt", "one", "Create")

    with pytest.raises(GitHubError) as caught:
        target.update_file(
            "repo/name", "a.txt", "two", "Update", "stale-sha"
        )

    assert caught.value.status == 409
    assert "SHA does not match" in str(caught.value)
    assert created["content"]["sha"] == client.files["a.txt"]["sha"]


@pytest.mark.parametrize("status", [401, 403, 404, 409, 422])
def test_g6_github_errors_remain_actionable(github_client, status):
    error = GitHubError(status, "repository mutation failed", request_id="request-6")
    target = Controller(None, client=github_client([error]))

    with pytest.raises(GitHubError) as caught:
        target.dispatch_repository("repo/name", "refresh")

    assert caught.value.status == status
    assert "repository mutation failed" in str(caught.value)
    assert "request-6" in str(caught.value)


def test_rehearsal_file_content_is_encoded_locally():
    client = RepositoryMutationClient()
    target = Controller(None, client=client)

    target.create_file("repo/name", "binary.dat", b"\x00\xff", "Create")

    assert client.files["binary.dat"]["content"] == base64.b64encode(
        b"\x00\xff"
    ).decode()
