from gway.tokens import tokenize
from tests.github_support import GitHubEvidenceController, REPOSITORY, pull_request


def merged_pr():
    return pull_request(
        state="closed",
        merged=True,
        merge_commit_sha="merge-sha",
        head={"sha": "head-sha"},
        base={"ref": "main"},
    )


def rollout_controller(**evidence):
    evidence.setdefault("pr", merged_pr())
    evidence.setdefault("issue_targets", [10])
    return GitHubEvidenceController(**evidence)


def test_rollout_reports_open_before_merge():
    result = GitHubEvidenceController().check_rollout(REPOSITORY, 10)
    assert result["state"] == "open"
    assert result["merged"]["value"] is False
    assert result["main"]["value"] is False


def test_rollout_distinguishes_stacked_merge_not_on_main():
    result = rollout_controller(on_main=False).check_rollout(REPOSITORY, 10)
    assert result["state"] == "merged-not-main"
    assert result["merged"]["value"] is True
    assert result["main"]["value"] is False
    assert result["diagnostic_target"]["stage"] == "main"


def test_rollout_reports_on_main_while_watchtower_is_behind():
    result = rollout_controller(accepted=False).check_rollout(REPOSITORY, 10)
    assert result["state"] == "on-main"
    assert result["main"]["value"] is True
    assert result["watchtower"]["certified"] is False
    assert result["diagnostic_target"]["stage"] == "watchtower"


def test_rollout_certification_accepts_newer_watchtower_revision():
    result = rollout_controller().check_rollout(REPOSITORY, 10)
    assert result["state"] == "certified"
    assert result["watchtower"]["certified"] is True
    assert result["watchtower"]["accepted_sha"] == "accepted-sha"
    assert result["watchtower"]["required_stage"] == "0-gway"
    assert result["watchtower"]["run_id"] == "123"


def test_arthexis_rollout_requires_arthexis_stage():
    result = rollout_controller().check_rollout("arthexis/arthexis", 10)
    assert result["state"] == "certified"
    assert result["watchtower"]["required_stage"] == "1-arthexis"


def test_rollout_issue_targeting_includes_merged_prs():
    controller = rollout_controller()
    result = controller.check_rollout(REPOSITORY, issue=1346, serial=True)
    assert result["issue"] == 1346
    assert result["targets"] == [10]
    assert controller.issue_state_calls == ["all"]


def test_observe_rollout_exposes_ancestry_and_manifest():
    result = rollout_controller().observe_rollout(REPOSITORY, 10)
    assert result["check"]["state"] == "certified"
    assert result["main_compare"]["status"] == "ahead"
    assert result["certification_compare"]["status"] == "ahead"
    assert result["watchtower_manifest"]["gway_sha"] == "accepted-sha"


def test_rollout_operations_are_read_only_semantic_operations(gateway):
    assert gateway.operation_routes.expand(gateway, tokenize("github check rollout")) is True
    for name in ("github.check_rollout", "github.observe_rollout"):
        operation = gateway.ops.resolve(name)
        assert operation is not None
        assert operation.mutates is False
        assert {"github", "source", "read"} <= set(
            operation.__gway_metadata__["topics"]
        )
