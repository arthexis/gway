from types import SimpleNamespace

import pytest

from gway.githubcheck import Controller
from gway.tokens import tokenize
import sampler.github.checks as github_checks


class TimelineClient:
    def __init__(self, events):
        self.events = events
        self.calls = []

    def pages(self, path, *, params=None):
        self.calls.append((path, params))
        yield SimpleNamespace(data=self.events)


def _cross_reference(number, *, state="open", repository="arthexis/gway", merged_at=None):
    return {
        "event": "cross-referenced",
        "source": {
            "type": "issue",
            "issue": {
                "number": number,
                "title": f"PR {number}",
                "state": state,
                "draft": False,
                "html_url": f"https://github.com/{repository}/pull/{number}",
                "repository": {"full_name": repository},
                "pull_request": {
                    "html_url": f"https://github.com/{repository}/pull/{number}",
                    "merged_at": merged_at,
                },
            },
        },
    }


def test_issue_prs_uses_same_repository_github_cross_references_only():
    client = TimelineClient(
        [
            _cross_reference(1347, state="closed", merged_at="2026-09-30T23:15:37Z"),
            _cross_reference(1351),
            _cross_reference(1351),
            _cross_reference(99, repository="other/repo"),
            {"event": "commented", "source": {"type": "issue"}},
        ]
    )
    controller = Controller(None, client=client)

    assert controller.issue_prs("arthexis/gway", 1346) == [
        {
            "number": 1351,
            "title": "PR 1351",
            "state": "open",
            "draft": False,
            "merged_at": None,
            "url": "https://github.com/arthexis/gway/pull/1351",
            "relationship": "cross-referenced",
        }
    ]
    assert controller.issue_prs("arthexis/gway", 1346, state="all")[0]["number"] == 1347
    assert client.calls[0] == (
        "/repos/arthexis/gway/issues/1346/timeline",
        {"per_page": 100},
    )


def test_issue_prs_returns_empty_when_github_has_no_linked_prs():
    controller = Controller(None, client=TimelineClient([{"event": "commented"}]))
    assert controller.issue_prs("arthexis/gway", 9000) == []


def test_issue_prs_rejects_unknown_state():
    controller = Controller(None, client=TimelineClient([]))
    with pytest.raises(ValueError, match="open, closed, or all"):
        controller.issue_prs("arthexis/gway", 1346, state="pending")


class TargetController(Controller):
    def __init__(self, targets):
        super().__init__(None, client=object())
        self.targets = targets
        self.checked = []

    def issue_prs(self, repository, issue, state="open"):
        assert state == "open"
        return [{"number": number} for number in self.targets]

    def _check_ci_pull(self, repository, pull):
        self.checked.append(pull)
        return {"repository": repository, "pr": pull, "state": "passed"}


def test_check_ci_issue_uses_selector_and_parallel_fanout(monkeypatch):
    created = []

    class FakeExecutor:
        def __init__(self, max_workers):
            created.append(max_workers)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def map(self, function, values):
            return [function(value) for value in values]

    monkeypatch.setattr(github_checks, "ThreadPoolExecutor", FakeExecutor)
    controller = TargetController([1351, 1354])

    result = controller.check_ci("arthexis/gway", issue=1346)

    assert created == [2]
    assert result["issue"] == 1346
    assert result["targets"] == [1351, 1354]
    assert [item["pr"] for item in result["pulls"]] == [1351, 1354]


def test_check_ci_serial_avoids_parallel_executor(monkeypatch):
    class UnexpectedExecutor:
        def __init__(self, *args, **kwargs):
            raise AssertionError("serial mode must not create an executor")

    monkeypatch.setattr(github_checks, "ThreadPoolExecutor", UnexpectedExecutor)
    controller = TargetController([1351, 1354])

    result = controller.check_ci("arthexis/gway", issue=1346, serial=True)

    assert controller.checked == [1351, 1354]
    assert result["targets"] == [1351, 1354]


def test_check_ci_issue_requires_at_least_one_related_open_pr():
    controller = TargetController([])
    with pytest.raises(ValueError, match="at least one pull target or --issue"):
        controller.check_ci("arthexis/gway", issue=1346)


def test_check_ci_rejects_mixed_explicit_and_issue_targets():
    controller = TargetController([1351])
    with pytest.raises(ValueError, match="mutually exclusive"):
        controller.check_ci("arthexis/gway", 1351, issue=1346)


def test_issue_prs_is_registered_as_read_only_semantic_operation(gateway):
    assert gateway.operation_routes.expand(
        gateway,
        tokenize("github issue prs"),
    ) is True

    operation = gateway.ops.resolve("github.issue_prs")
    assert operation is not None
    assert operation.mutates is False
    assert {"github", "source", "read"} <= set(operation.__gway_metadata__["topics"])
