from tests.github_support import GitHubEvidenceController, REPOSITORY, pull_request


def test_check_pr_is_intrinsic_overview():
    controller = GitHubEvidenceController(
        pr=pull_request(labels=[{"name": "integration"}, {"name": "on-hold"}])
    )
    result = controller.check_pr(REPOSITORY, 10)
    assert result["state"] == "ready"
    assert result["on_hold"] is True
    assert result["labels"] == ["integration", "on-hold"]
    assert result["head"]["sha"] == "head"


def test_check_reviews_distinguishes_unresolved_threads_from_required_review():
    controller = GitHubEvidenceController(
        reviews=[{"user": {"login": "reviewer"}, "state": "APPROVED"}],
        threads=[{"id": "thread-1", "isResolved": False, "isOutdated": False}],
        decision="APPROVED",
    )
    result = controller.check_reviews(REPOSITORY, 10)
    assert result["state"] == "unresolved"
    assert result["requirements"] == {
        "decision": "APPROVED",
        "required": True,
        "satisfied": True,
    }
    assert result["unresolved_thread_ids"] == ["thread-1"]


def test_check_reviews_reports_genuine_review_requirement():
    result = GitHubEvidenceController(decision="REVIEW_REQUIRED").check_reviews(
        REPOSITORY, 10
    )
    assert result["state"] == "review-required"
    assert result["requirements"]["satisfied"] is False
    assert result["diagnostic_target"] == {"kind": "github-reviews", "pr": 10}


def test_check_freshness_exposes_expected_head_update_action():
    result = GitHubEvidenceController(
        compare={"ahead_by": 2, "behind_by": 3}
    ).check_freshness(REPOSITORY, 10)
    assert result["state"] == "behind"
    assert result["updatable"] is True
    assert result["action"] == {"kind": "update-branch", "expected_head_sha": "head"}


def test_check_freshness_identifies_conflict():
    result = GitHubEvidenceController(
        pr=pull_request(mergeable=False, mergeable_state="dirty"),
        compare={"ahead_by": 2, "behind_by": 3},
    ).check_freshness(REPOSITORY, 10)
    assert result["state"] == "conflict"
    assert result["updatable"] is False


def test_check_merge_requires_direct_merge_once_immediately_mergeable():
    result = GitHubEvidenceController().check_merge(REPOSITORY, 10)
    assert result["state"] == "ready"
    assert result["authorization"]["state"] == "direct-merge-required"
    assert result["action"] == {"kind": "merge-pull", "expected_head_sha": "head"}


def test_check_merge_uses_auto_merge_while_policy_still_blocks_merge():
    result = GitHubEvidenceController(
        pr=pull_request(mergeable_state="blocked")
    ).check_merge(REPOSITORY, 10)
    assert result["state"] == "blocked"
    assert result["authorization"]["state"] == "not-authorized"
    assert result["action"]["kind"] == "enable-auto-merge"


def test_check_merge_preserves_native_auto_merge_authorization():
    result = GitHubEvidenceController(
        pr=pull_request(auto_merge={"merge_method": "SQUASH"})
    ).check_merge(REPOSITORY, 10)
    assert result["state"] == "ready"
    assert result["authorization"]["state"] == "native-auto-merge"
    assert "action" not in result


def test_all_core_checks_share_issue_targeting_contract():
    controller = GitHubEvidenceController()
    for check in (
        controller.check_pr,
        controller.check_reviews,
        controller.check_freshness,
        controller.check_merge,
        controller.check_ci,
    ):
        result = check(REPOSITORY, issue=1346, serial=True)
        assert result["issue"] == 1346
        assert result["targets"] == [10, 11]
        assert [item["pr"] for item in result["pulls"]] == [10, 11]
