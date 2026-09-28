from types import SimpleNamespace

from gway.githubops import Controller


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, path, *, params=None, json=None, headers=None):
        self.calls.append((method, path, params))
        return SimpleNamespace(data=self.responses.pop(0))

    def pages(self, path, *, params=None):
        self.calls.append(("PAGES", path, params))
        for data in self.responses:
            yield SimpleNamespace(data=data)


def controller(*responses):
    return Controller(None, client=FakeClient(responses))


def test_repository_and_status_are_read_only_views():
    repo = {
        "full_name": "arthexis/gway",
        "default_branch": "main",
        "private": False,
        "archived": False,
        "disabled": False,
        "pushed_at": "2026-09-28T00:00:00Z",
    }
    target = controller(repo)

    assert target.status("arthexis/gway") == {
        "repository": "arthexis/gway",
        "default_branch": "main",
        "private": False,
        "archived": False,
        "disabled": False,
        "pushed_at": "2026-09-28T00:00:00Z",
    }
    assert target._client.calls == [("GET", "/repos/arthexis/gway", None)]


def test_branches_collect_paginated_results():
    target = controller([{"name": "main"}], [{"name": "feature"}])

    assert target.branches("arthexis/gway") == [
        {"name": "main"},
        {"name": "feature"},
    ]
    assert target._client.calls == [
        ("PAGES", "/repos/arthexis/gway/branches", {"per_page": 100})
    ]


def test_commit_file_tree_ref_and_tags_map_to_rest_resources():
    target = controller(
        {"sha": "abc"},
        {"name": "README.md"},
        {"tree": []},
        {"ref": "refs/heads/main"},
        [{"name": "v1"}],
    )

    assert target.commit("arthexis/gway", "abc")["sha"] == "abc"
    assert target.file("arthexis/gway", "docs/a b.md", ref="main")["name"] == "README.md"
    assert target.tree("arthexis/gway", "abc", recursive=True) == {"tree": []}
    assert target.ref("arthexis/gway", "refs/heads/main")["ref"] == "refs/heads/main"
    assert target.tags("arthexis/gway") == [{"name": "v1"}]

    assert target._client.calls == [
        ("GET", "/repos/arthexis/gway/commits/abc", None),
        ("GET", "/repos/arthexis/gway/contents/docs/a%20b.md", {"ref": "main"}),
        ("GET", "/repos/arthexis/gway/git/trees/abc", {"recursive": "1"}),
        ("GET", "/repos/arthexis/gway/git/ref/heads/main", None),
        ("PAGES", "/repos/arthexis/gway/tags", {"per_page": 100}),
    ]


def test_refs_preserve_empty_ref_segment_when_listing_all():
    target = controller([])

    assert target.refs("arthexis/gway") == []
    assert target._client.calls == [
        ("PAGES", "/repos/arthexis/gway/git/matching-refs/", None)
    ]


def test_repository_requires_owner_name_shape():
    target = controller({})

    try:
        target.repository("gway")
    except ValueError as error:
        assert "owner/name" in str(error)
    else:
        raise AssertionError("expected repository validation")
