from gway.tokens import tokenize
from tests.github_support import GitHubEvidenceController, REPOSITORY


class StatusEvidenceController(GitHubEvidenceController):
    """Inject already-normalized checks so these tests exercise policy only."""

    def __init__(self):
        super().__init__()
        self.rollout_result = {
            "state": "open",
            "watchtower": {"available": True},
        }
        self.pr_result = {"state": "ready", "on_hold": False}
        self.reviews_result = {
            "state": "clear",
            "diagnostic_target": {"kind": "github-reviews", "pr": 10},
        }
        self.freshness_result = {"state": "up-to-date"}
        self.ci_result = {"state": "passed"}
        self.merge_result = {
            "state": "ready",
            "authorization": {"state": "native-auto-merge"},
        }

    def _check_rollout_pull(self, repository, pull):
        return dict(self.rollout_result)

    def _check_pr_pull(self, repository, pull):
        return dict(self.pr_result)

    def _check_reviews_pull(self, repository, pull):
        return dict(self.reviews_result)

    def _check_freshness_pull(self, repository, pull):
        return dict(self.freshness_result)

    def _check_ci_pull(self, repository, pull):
        return dict(self.ci_result)

    def _check_merge_pull(self, repository, pull):
        return dict(self.merge_result)


def test_certified_is_terminal_done_contract():
    controller = StatusEvidenceController()
    controller.rollout_result = {
        "state": "certified",
        "watchtower": {"available": True},
    }

    result = controller.status(REPOSITORY, 10)

    assert result["status"] == "certified"
    assert result["disposition"] == "done"
    assert "action" not in result


def test_automatic_states_expose_an_action_contract():
    controller = StatusEvidenceController()
    controller.freshness_result = {
        "state": "behind",
        "action": {"kind": "update-branch", "expected_head_sha": "head"},
    }

    result = controller.status(REPOSITORY, 10)

    assert result["disposition"] == "auto"
    assert result["action"]["kind"] == "update-branch"


def test_failed_ci_escalates_with_observable_target():
    controller = StatusEvidenceController()
    controller.ci_result = {
        "state": "failed",
        "diagnostic_target": {
            "kind": "github-ci",
            "run_id": 30,
            "job_id": 20,
        },
    }

    result = controller.status(REPOSITORY, 10)

    assert result["status"] == "ci-failed"
    assert result["disposition"] == "escalate"
    assert result["diagnostic_target"]["kind"] == "github-ci"


def test_unresolved_review_threads_are_conservative_escalation():
    controller = StatusEvidenceController()
    controller.reviews_result = {
        "state": "unresolved",
        "diagnostic_target": {"kind": "github-reviews", "pr": 10},
    }

    result = controller.status(REPOSITORY, 10)

    assert result["status"] == "review-threads-unresolved"
    assert result["disposition"] == "escalate"
    assert result["diagnostic_target"]["kind"] == "github-reviews"


def test_merge_actions_preserve_check_supplied_expected_head_guard():
    controller = StatusEvidenceController()
    controller.merge_result = {
        "state": "ready",
        "authorization": {"state": "direct-merge-required"},
        "action": {"kind": "merge-pull", "expected_head_sha": "head"},
    }

    result = controller.status(REPOSITORY, 10)

    assert result["status"] == "merge-ready"
    assert result["disposition"] == "auto"
    assert result["action"] == {
        "kind": "merge-pull",
        "expected_head_sha": "head",
    }


def test_on_main_waits_for_watchtower_when_certification_is_available():
    controller = StatusEvidenceController()
    controller.rollout_result = {
        "state": "on-main",
        "watchtower": {"available": True},
        "diagnostic_target": {
            "kind": "github-rollout",
            "pr": 10,
            "stage": "watchtower",
        },
    }

    result = controller.status(REPOSITORY, 10)

    assert result["status"] == "certification-pending"
    assert result["disposition"] == "wait"
    assert result["diagnostic_target"]["stage"] == "watchtower"


def test_status_issue_targeting_includes_merged_linked_prs():
    controller = StatusEvidenceController()

    result = controller.status(REPOSITORY, issue=1346, serial=True)

    assert controller.issue_state_calls == ["all"]
    assert result["issue"] == 1346
    assert result["targets"] == [10, 11]


def test_repository_status_without_pr_target_remains_backward_compatible():
    result = StatusEvidenceController().status(REPOSITORY)

    assert result == {
        "repository": REPOSITORY,
        "default_branch": "main",
        "private": False,
        "archived": False,
        "disabled": False,
        "pushed_at": None,
    }


def test_status_is_a_read_only_semantic_operation(gateway):
    assert gateway.operation_routes.expand(gateway, tokenize("github status")) is True

    operation = gateway.ops.resolve("github.status")
    assert operation is not None
    assert operation.mutates is False
    assert {"github", "source", "read"} <= set(
        operation.__gway_metadata__["topics"]
    )
