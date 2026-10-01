from sampler.github.checks import Controller


class CheckController(Controller):
    def __init__(self, pr=None, *, reviews=None, threads=None, decision=None, compare=None):
        super().__init__(None, client=object())
        self.pr = pr or {}
        self.review_items = reviews or []
        self.thread_items = threads or []
        self.decision = decision
        self.compare_result = compare or {"ahead_by": 1, "behind_by": 0}
        self.checked = []

    def pull(self, repository, number):
        return self.pr

    def reviews(self, repository, number):
        return self.review_items

    def review_threads(self, repository, number, unresolved=False):
        return self.thread_items if unresolved else self.thread_items

    def review_decision(self, repository, number):
        return self.decision

    def compare(self, repository, base, head):
        return self.compare_result

    def issue_prs(self, repository, issue, state="open"):
        return [{"number": 10}, {"number": 11}]


def _pr(**updates):
    value = {
        "state": "open",
        "draft": False,
        "merged": False,
        "mergeable": True,
        "mergeable_state": "clean",
        "auto_merge": None,
        "labels": [],
        "base": {"ref": "main", "sha": "base"},
        "head": {"ref": "feature", "sha": "head"},
        "html_url": "https://github.com/arthexis/gway/pull/10",
    }
    value.update(updates)
    return value


def test_check_pr_is_intrinsic_overview():
    controller = CheckController(_pr(labels=[{"name": "integration"}, {"name": "on-hold"}]))
    result = controller.check_pr("arthexis/gway", 10)
    assert result["state"] == "ready"
    assert result["on_hold"] is True
    assert result["labels"] == ["integration", "on-hold"]
    assert result["head"]["sha"] == "head"


def test_check_reviews_distinguishes_unresolved_threads_from_required_review():
    controller = CheckController(
        _pr(),
        reviews=[{"user": {"login": "reviewer"}, "state": "APPROVED"}],
        threads=[{"id": "thread-1", "isResolved": False, "isOutdated": False}],
        decision="APPROVED",
    )
    result = controller.check_reviews("arthexis/gway", 10)
    assert result["state"] == "unresolved"
    assert result["requirements"] == {
        "decision": "APPROVED",
        "required": True,
        "satisfied": True,
    }
    assert result["unresolved_thread_ids"] == ["thread-1"]


def test_check_reviews_reports_genuine_review_requirement():
    controller = CheckController(_pr(), decision="REVIEW_REQUIRED")
    result = controller.check_reviews("arthexis/gway", 10)
    assert result["state"] == "review-required"
    assert result["requirements"]["satisfied"] is False
    assert result["diagnostic_target"] == {"kind": "github-reviews", "pr": 10}


def test_check_freshness_exposes_expected_head_update_action():
    controller = CheckController(_pr(), compare={"ahead_by": 2, "behind_by": 3})
    result = controller.check_freshness("arthexis/gway", 10)
    assert result["state"] == "behind"
    assert result["updatable"] is True
    assert result["action"] == {"kind": "update-branch", "expected_head_sha": "head"}


def test_check_freshness_identifies_conflict():
    controller = CheckController(
        _pr(mergeable=False, mergeable_state="dirty"),
        compare={"ahead_by": 2, "behind_by": 3},
    )
    result = controller.check_freshness("arthexis/gway", 10)
    assert result["state"] == "conflict"
    assert result["updatable"] is False


def test_check_merge_requires_direct_merge_once_immediately_mergeable():
    controller = CheckController(_pr(mergeable=True, mergeable_state="clean", auto_merge=None))
    result = controller.check_merge("arthexis/gway", 10)
    assert result["state"] == "ready"
    assert result["authorization"]["state"] == "direct-merge-required"
    assert result["action"] == {"kind": "merge-pull", "expected_head_sha": "head"}


def test_check_merge_uses_auto_merge_while_policy_still_blocks_merge():
    controller = CheckController(
        _pr(mergeable=True, mergeable_state="blocked", auto_merge=None)
    )
    result = controller.check_merge("arthexis/gway", 10)
    assert result["state"] == "blocked"
    assert result["authorization"]["state"] == "not-authorized"
    assert result["action"] == {
        "kind": "enable-auto-merge",
        "expected_head_sha": "head",
    }


def test_check_merge_preserves_native_auto_merge_authorization():
    controller = CheckController(
        _pr(mergeable=True, auto_merge={"merge_method": "SQUASH"})
    )
    result = controller.check_merge("arthexis/gway", 10)
    assert result["state"] == "ready"
    assert result["authorization"]["state"] == "native-auto-merge"
    assert "action" not in result


def test_all_core_checks_share_issue_targeting_shape():
    controller = CheckController(_pr(), decision=None)
    for check in (
        controller.check_pr,
        controller.check_reviews,
        controller.check_freshness,
        controller.check_merge,
    ):
        result = check("arthexis/gway", issue=1346, serial=True)
        assert result["issue"] == 1346
        assert result["targets"] == [10, 11]
        assert [item["pr"] for item in result["pulls"]] == [10, 11]
