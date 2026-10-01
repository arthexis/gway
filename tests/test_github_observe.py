from gway.tokens import tokenize
from sampler.github.observe import Controller


class ObserveController(Controller):
    def __init__(self):
        super().__init__(None, client=object())
        self._pr = {
            "number": 10,
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

    def pull(self, repository, number):
        return dict(self._pr)

    def issue_prs(self, repository, issue, state="open"):
        return [{"number": 10}, {"number": 11}]

    def reviews(self, repository, number):
        return [
            {
                "id": 1,
                "state": "APPROVED",
                "user": {"login": "reviewer"},
            }
        ]

    def review_decision(self, repository, number):
        return "APPROVED"

    def review_threads(self, repository, number, unresolved=False):
        return [
            {
                "id": "thread-1",
                "isResolved": False,
                "isOutdated": False,
                "comments": {"nodes": [{"body": "Please adjust this"}]},
            }
        ]

    def review_comments(self, repository, number):
        return [{"id": 2, "body": "Please adjust this"}]

    def compare(self, repository, base, head):
        return {
            "status": "behind",
            "ahead_by": 2,
            "behind_by": 3,
            "files": [{"filename": "gway.py"}],
        }

    def checks(self, repository, ref):
        return [
            {
                "id": 5,
                "name": "python / Python compatibility",
                "conclusion": "success",
            }
        ]

    def run(self, repository, run):
        return {
            "id": int(run),
            "name": "Python compatibility",
            "status": "completed",
            "conclusion": "failure",
        }

    def jobs(self, repository, run):
        return [
            {
                "id": 20,
                "run_id": int(run),
                "name": "tests",
                "conclusion": "failure",
            },
            {
                "id": 21,
                "run_id": int(run),
                "name": "compat",
                "conclusion": "success",
            },
        ]

    def job(self, repository, job):
        if int(job) == 20:
            return {
                "id": 20,
                "run_id": 30,
                "name": "tests",
                "conclusion": "failure",
                "steps": [{"name": "pytest", "conclusion": "failure"}],
            }
        return {
            "id": 21,
            "run_id": 30,
            "name": "compat",
            "conclusion": "success",
        }

    def job_logs(self, repository, job):
        return {
            "status": 200,
            "content_type": "text/plain",
            "content": b"failure details\n",
        }

    def artifacts(self, repository, run, name=None):
        return [{"id": 40, "name": "gway-ci-result"}]

    def artifact_json(self, repository, artifact, filename="ci-result.json"):
        return {"state": "failed", "phase": "tests"}


def test_observe_reviews_preserves_thread_evidence_and_compact_check():
    controller = ObserveController()
    result = controller.observe_reviews("arthexis/gway", 10)
    assert result["check"]["state"] == "unresolved"
    assert result["review_decision"] == "APPROVED"
    assert result["threads"][0]["id"] == "thread-1"
    assert result["comments"][0]["id"] == 2


def test_observe_freshness_returns_compare_evidence():
    controller = ObserveController()
    result = controller.observe_freshness("arthexis/gway", 10)
    assert result["check"]["state"] == "behind"
    assert result["compare"]["files"][0]["filename"] == "gway.py"


def test_observe_merge_returns_provider_requirements_evidence():
    controller = ObserveController()
    result = controller.observe_merge("arthexis/gway", 10)
    assert result["check"]["authorization"]["state"] == "direct-merge-required"
    assert result["review_decision"] == "APPROVED"
    assert result["checks"][0]["name"] == "python / Python compatibility"


def test_observe_ci_direct_job_uses_diagnostic_target_and_decodes_log():
    controller = ObserveController()
    result = controller.observe_ci("arthexis/gway", job=20)
    assert result["run"] == 30
    assert result["job"] == 20
    assert len(result["jobs"]) == 1
    assert result["jobs"][0]["log"]["content"] == "failure details\n"
    assert result["canonical_results"][0]["result"]["state"] == "failed"


def test_observe_ci_failed_mode_does_not_download_success_logs():
    controller = ObserveController()
    result = controller.observe_ci("arthexis/gway", run=30)
    assert "log" in result["jobs"][0]
    assert "log" not in result["jobs"][1]


def test_observe_ci_rejects_mixed_pr_and_diagnostic_targets():
    controller = ObserveController()
    try:
        controller.observe_ci("arthexis/gway", 10, run=30)
    except ValueError as exc:
        assert "mutually exclusive" in str(exc)
    else:
        raise AssertionError("mixed CI target modes must be rejected")


def test_observations_share_issue_targeting_shape():
    controller = ObserveController()
    for operation in (
        controller.observe_pr,
        controller.observe_reviews,
        controller.observe_freshness,
        controller.observe_merge,
    ):
        result = operation("arthexis/gway", issue=1346, serial=True)
        assert result["issue"] == 1346
        assert result["targets"] == [10, 11]
        assert [item["pr"] for item in result["pulls"]] == [10, 11]


def test_observe_operations_are_read_only_semantic_operations(gateway):
    assert gateway.operation_routes.expand(
        gateway,
        tokenize("github observe ci"),
    ) is True

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
