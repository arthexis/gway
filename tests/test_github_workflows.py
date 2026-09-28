from types import SimpleNamespace

from gway.githubops import Controller


class FakeClient:
    def __init__(self, responses=(), pages=()):
        self.responses = list(responses)
        self.page_data = list(pages)
        self.calls = []

    def request(self, method, path, *, params=None, json=None, headers=None):
        self.calls.append((method, path, params))
        return SimpleNamespace(data=self.responses.pop(0))

    def pages(self, path, *, params=None):
        self.calls.append(("PAGES", path, params))
        for data in self.page_data:
            yield SimpleNamespace(data=data)


def test_workflows_unwrap_definition_collection():
    client = FakeClient(responses=[{"workflows": [{"id": 1, "path": ".github/workflows/ci.yml"}]}])
    target = Controller(None, client=client)

    assert target.workflows("arthexis/gway") == [
        {"id": 1, "path": ".github/workflows/ci.yml"}
    ]
    assert client.calls == [
        (
            "GET",
            "/repos/arthexis/gway/actions/workflows",
            {"per_page": 100},
        )
    ]


def test_workflow_accepts_file_name_identifier():
    client = FakeClient(responses=[{"id": 1, "name": "CI"}])
    target = Controller(None, client=client)

    assert target.workflow("arthexis/gway", "ci.yml")["name"] == "CI"
    assert client.calls[-1][1] == "/repos/arthexis/gway/actions/workflows/ci.yml"


def test_releases_paginate_and_support_id_tag_and_latest():
    client = FakeClient(
        responses=[
            {"id": 7},
            {"tag_name": "v2.0"},
            {"tag_name": "v2.1"},
        ],
        pages=[[{"id": 1}], [{"id": 2}]],
    )
    target = Controller(None, client=client)

    assert target.releases("arthexis/gway") == [{"id": 1}, {"id": 2}]
    assert target.release("arthexis/gway", 7) == {"id": 7}
    assert target.release_tag("arthexis/gway", "v2.0")["tag_name"] == "v2.0"
    assert target.latest_release("arthexis/gway")["tag_name"] == "v2.1"


def test_workflow_and_release_reads_are_non_mutating(gateway):
    names = {
        "github.workflows",
        "github.workflow",
        "github.releases",
        "github.release",
        "github.release_tag",
        "github.latest_release",
    }
    for name in names:
        operation = gateway.ops.resolve(name)
        assert operation is not None
        assert operation.mutates is False
        assert {"github", "source", "read"} <= set(
            operation.__gway_metadata__["topics"]
        )
