import pytest

from gway.tokens import tokenize
from tests.github_support import GitHubEvidenceController, REPOSITORY


def review_evidence():
    return {
        "reviews": [{"id": 1, "state": "APPROVED", "user": {"login": "reviewer"}}],
        "threads": [
            {
                "id": "thread-1",
                "isResolved": False,
                "isOutdated": False,
                "comments": {"nodes": [{"body": "Please adjust this"}]},
            }
        ],
        "decision": "APPROVED",
    }


def test_observe_reviews_preserves_thread_evidence_and_compact_check():
    result = GitHubEvidenceController(**review_evidence()).observe_reviews(REPOSITORY, 10)
    assert result["check"]["state"] == "unresolved"
    assert result["review_decision"] == "APPROVED"
    assert result["threads"][0]["id"] == "thread-1"
    assert result["comments"][0]["id"] == 2


def test_observe_freshness_returns_compare_evidence():
    result = GitHubEvidenceController(
        compare={
            "status": "behind",
            "ahead_by": 2,
            "behind_by": 3,
            "files": [{"filename": "gway.py"}],
        }
    ).observe_freshness(REPOSITORY, 10)
    assert result["check"]["state"] == "behind"
    assert result["compare"]["files"][0]["filename"] == "gway.py"


def test_observe_merge_returns_provider_requirements_evidence():
    result = GitHubEvidenceController(decision="APPROVED").observe_merge(REPOSITORY, 10)
    assert result["check"]["authorization"]["state"] == "direct-merge-required"
    assert result["review_decision"] == "APPROVED"
    assert result["checks"][0]["name"] == "python / Python compatibility"


def test_observe_ci_direct_job_uses_diagnostic_target_and_decodes_log():
    result = GitHubEvidenceController().observe_ci(REPOSITORY, job=20)
    assert result["run"] == 30
    assert result["job"] == 20
    assert len(result["jobs"]) == 1
    assert result["jobs"][0]["log"]["content"] == "failure details\n"
    assert result["check_runs"][0]["annotations"][0]["path"] == "tests/test_example.py"
    assert result["canonical_results"][0]["result"]["state"] == "failed"


def test_observe_ci_failed_mode_does_not_download_success_logs():
    result = GitHubEvidenceController().observe_ci(REPOSITORY, run=30)
    assert "log" in result["jobs"][0]
    assert "log" not in result["jobs"][1]


def test_observe_ci_rejects_mixed_pr_and_diagnostic_targets():
    with pytest.raises(ValueError, match="mutually exclusive"):
        GitHubEvidenceController().observe_ci(REPOSITORY, 10, run=30)


def test_observations_share_issue_targeting_contract():
    controller = GitHubEvidenceController(**review_evidence())
    for operation in (
        controller.observe_pr,
        controller.observe_reviews,
        controller.observe_freshness,
        controller.observe_merge,
    ):
        result = operation(REPOSITORY, issue=1346, serial=True)
        assert result["issue"] == 1346
        assert result["targets"] == [10, 11]
        assert [item["pr"] for item in result["pulls"]] == [10, 11]


def test_observe_operations_are_read_only_semantic_operations(gateway):
    assert gateway.operation_routes.expand(gateway, tokenize("github observe ci")) is True

    for name in (
        "github.observe_pr",
        "github.observe_reviews",
        "github.observe_freshness",
        "github.observe_merge",
        "github.observe_ci",
    ):
        operation = gateway.ops.resolve(name)
        assert operation is not None
        assert operation.mutates is False
        assert {"github", "source", "read"} <= set(
            operation.__gway_metadata__["topics"]
        )
