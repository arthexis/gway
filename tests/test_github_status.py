from gway.tokens import tokenize
from sampler.github.status import Controller


class StatusController(Controller):
    def __init__(self):
        super().__init__(None, client=object())
        self.rollout = {
            "state": "open",
            "watchtower": {"available": True},
        }
        self.pr = {"state": "ready", "on_hold": False}
        self.reviews_state = {
            "state": "clear",
            "diagnostic_target": {"kind": "github-reviews", "pr": 10},
        }
        self.freshness = {"state": "up-to-date"}
        self.ci = {"state": "passed"}
        self.merge = {
            "state": "ready",
            "authorization": {"state": "native-auto-merge"},
        }
        self.issue_state_requested = None

    def _check_rollout_pull(self, repository, pull):
        return dict(self.rollout)

    def _check_pr_pull(self, repository, pull):
        return dict(self.pr)

    def _check_reviews_pull(self, repository, pull):
        return dict(self.reviews_state)

    def _check_freshness_pull(self, repository, pull):
        return dict(self.freshness)

    def _check_ci_pull(self, repository, pull):
        return dict(self.ci)

    def _check_merge_pull(self, repository, pull):
        return dict(self.merge)

    def issue_prs(self, repository, issue, state="open"):
        self.issue_state_requested = state
        return [{"number": 10}, {"number": 11}]


def test_certified_is_terminal_done_contract():
    controller = StatusController()
    controller.rollout = {"state": "certified", "watchtower": {"available": True}}

    result = controller.status("arthexis/gway", 10)

    assert result["status"] == "certified"
    assert result["disposition"] == "done"
    assert "action" not in result


def test_automatic_states_expose_an_action_contract():
    controller = StatusController()
    controller.freshness = {
        "state": "behind",
        "action": {"kind": "update-branch", "expected_head_sha": "head"},
    }

    result = controller.status("arthexis/gway", 10)

    assert result["disposition"] == "auto"
    assert result["action"]["kind"] == "update-branch"


def test_failed_ci_escalates_with_observable_target():
    controller = StatusController()
    controller.ci = {
        "state": "failed",
        "diagnostic_target": {
            "kind": "github-ci",
            "run_id": 30,
            "job_id": 20,
        },
    }

    result = controller.status("arthexis/gway", 10)

    assert result["status"] == "ci-failed"
    assert result["disposition"] == "escalate"
    assert result["diagnostic_target"] == {
        "kind": "github-ci",
        "run_id": 30,
        "job_id": 20,
    }


def test_unresolved_review_threads_are_conservative_escalation():
    controller = StatusController()
    controller.reviews_state = {
        "state": "unresolved",
        "diagnostic_target": {"kind": "github-reviews", "pr": 10},
    }

    result = controller.status("arthexis/gway", 10)

    assert result["status"] == "review-threads-unresolved"
    assert result["disposition"] == "escalate"
    assert result["diagnostic_target"]["kind"] == "github-reviews"


def test_merge_actions_preserve_check_supplied_expected_head_guard():
    controller = StatusController()
    controller.merge = {
        "state": "ready",
        "authorization": {"state": "direct-merge-required"},
        "action": {"kind": "merge-pull", "expected_head_sha": "head"},
    }

    result = controller.status("arthexis/gway", 10)

    assert result["status"] == "merge-ready"
    assert result["disposition"] == "auto"
    assert result["action"] == {
        "kind": "merge-pull",
        "expected_head_sha": "head",
    }


def test_on_main_waits_for_watchtower_when_certification_is_available():
    controller = StatusController()
    controller.rollout = {
        "state": "on-main",
        "watchtower": {"available": True},
        "diagnostic_target": {
            "kind": "github-rollout",
            "pr": 10,
            "stage": "watchtower",
        },
    }

    result = controller.status("arthexis/gway", 10)

    assert result["status"] == "certification-pending"
    assert result["disposition"] == "wait"
    assert result["diagnostic_target"]["stage"] == "watchtower"


def test_status_issue_targeting_includes_merged_linked_prs():
    controller = StatusController()

    result = controller.status("arthexis/gway", issue=1346, serial=True)

    assert controller.issue_state_requested == "all"
    assert result["issue"] == 1346
    assert result["targets"] == [10, 11]
    assert [item["pr"] for item in result["pulls"]] == [10, 11]


def test_repository_status_without_pr_target_remains_backward_compatible():
    class RepositoryStatusController(StatusController):
        def repository(self, repository):
            return {"default_branch": "main", "html_url": "https://example.test/repo"}

        def branch(self, repository, branch):
            return {"name": branch, "commit": {"sha": "main-sha"}}

    result = RepositoryStatusController().status("arthexis/gway")

    assert result["default_branch"] == "main"
    assert result["head_sha"] == "main-sha"


def test_status_is_a_read_only_semantic_operation(gateway):
    assert gateway.operation_routes.expand(gateway, tokenize("github status")) is True

    operation = gateway.ops.resolve("github.status")
    assert operation is not None
    assert operation.mutates is False
    assert {"github", "source", "read"} <= set(
        operation.__gway_metadata__["topics"]
    )
