from types import SimpleNamespace

from gway.githubops import Controller


class FakeClient:
    def __init__(self, pages=(), graphql=()):
        self.page_data = list(pages)
        self.graphql_data = list(graphql)
        self.calls = []

    def request(self, method, path, *, params=None, json=None, headers=None):
        self.calls.append((method, path, params))
        return SimpleNamespace(data={"number": 12})

    def pages(self, path, *, params=None):
        self.calls.append(("PAGES", path, params))
        for data in self.page_data:
            yield SimpleNamespace(data=data)

    def graphql(self, query, variables=None):
        self.calls.append(("GRAPHQL", variables.copy()))
        return SimpleNamespace(data=self.graphql_data.pop(0))


def test_pull_issue_comments_and_reviews_use_expected_resources():
    client = FakeClient(pages=[[{"number": 1}]])
    target = Controller(None, client=client)

    assert target.pulls("arthexis/gway") == [{"number": 1}]
    assert client.calls[-1] == (
        "PAGES",
        "/repos/arthexis/gway/pulls",
        {"state": "open", "per_page": 100},
    )

    assert target.pull("arthexis/gway", 12) == {"number": 12}
    assert client.calls[-1] == ("GET", "/repos/arthexis/gway/pulls/12", None)


def test_review_threads_paginate_and_filter_unresolved():
    first = {
        "data": {
            "repository": {
                "pullRequest": {
                    "reviewThreads": {
                        "nodes": [{"id": "one", "isResolved": True}],
                        "pageInfo": {"hasNextPage": True, "endCursor": "cursor"},
                    }
                }
            }
        }
    }
    second = {
        "data": {
            "repository": {
                "pullRequest": {
                    "reviewThreads": {
                        "nodes": [{"id": "two", "isResolved": False}],
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                    }
                }
            }
        }
    }
    client = FakeClient(graphql=[first, second])
    target = Controller(None, client=client)

    assert target.review_threads("arthexis/gway", 1218, unresolved=True) == [
        {"id": "two", "isResolved": False}
    ]
    assert client.calls[0][1] == {
        "owner": "arthexis",
        "name": "gway",
        "number": 1218,
        "after": None,
    }
    assert client.calls[1][1]["after"] == "cursor"


def test_collaboration_operations_are_non_mutating_source_reads(gateway):
    names = {
        "github.pulls",
        "github.pull",
        "github.issues",
        "github.issue",
        "github.comments",
        "github.reviews",
        "github.review_comments",
        "github.review_threads",
    }
    for name in names:
        operation = gateway.ops.resolve(name)
        assert operation is not None
        assert operation.mutates is False
        assert {"github", "source", "read"} <= set(
            operation.__gway_metadata__["topics"]
        )
