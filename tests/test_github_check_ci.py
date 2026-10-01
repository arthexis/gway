import io
import json
from types import SimpleNamespace
import zipfile

from gway.githubcheck import Controller
from gway.tokens import tokenize


class FakeClient:
    def __init__(self, responses, artifact=None):
        self.responses = list(responses)
        self.artifact = artifact
        self.calls = []

    def request(self, method, path, *, params=None, json=None, headers=None):
        self.calls.append((method, path, params))
        data = self.responses.pop(0)
        return SimpleNamespace(data=data, status=200, headers={}, next_url=None)

    def download_redirect(self, path):
        self.calls.append(("DOWNLOAD", path, None))
        return SimpleNamespace(data=self.artifact, status=200, headers={}, next_url=None)


def _artifact(value):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("ci-result.json", json.dumps(value))
    return stream.getvalue()


def test_check_ci_enriches_current_head_failure_from_canonical_artifact():
    client = FakeClient(
        [
            {"head": {"sha": "abc", "ref": "feature"}},
            {"workflow_runs": [{"id": 7, "name": "python", "head_sha": "abc", "status": "completed", "conclusion": "failure"}]},
            {"workflow_runs": []},
            {"workflow_runs": []},
            {"jobs": [{"id": 11, "name": "Tests", "status": "completed", "conclusion": "failure"}]},
            {"artifacts": [{"id": 22, "name": "gway-ci-result"}]},
        ],
        artifact=_artifact({"state": "failed", "phase": "tests", "tests": {"failed": 1}}),
    )
    result = Controller(None, client=client).check_ci("arthexis/gway", 1348)

    assert result["head_sha"] == "abc"
    assert result["state"] == "failed"
    assert result["current"] is True
    assert result["failure_kind"] == "ci"
    assert result["result"]["phase"] == "tests"
    assert result["diagnostic_target"] == {"kind": "github-ci", "run_id": 7, "job_id": 11}


def test_check_ci_includes_label_dispatched_run_for_current_pr_head():
    client = FakeClient(
        [
            {"head": {"sha": "abcdef123456", "ref": "feature"}},
            {"workflow_runs": []},
            {"workflow_runs": [{"id": 8, "name": "python", "event": "workflow_dispatch", "display_title": "PR #1348 @ abcdef123456", "head_sha": "base", "status": "completed", "conclusion": "success"}]},
            {"workflow_runs": []},
            {"jobs": [{"id": 12, "name": "Tests", "status": "completed", "conclusion": "success"}]},
            {"artifacts": []},
        ]
    )

    result = Controller(None, client=client).check_ci("arthexis/gway", 1348)

    assert result["state"] == "passed"
    assert result["current"] is True
    assert result["workflows"][0]["id"] == 8
    assert result["workflows"][0]["head_sha"] == "base"
    assert result["workflows"][0]["tested_head_sha"] == "abcdef123456"


def test_check_ci_never_promotes_stale_green_run_to_current_success():
    client = FakeClient(
        [
            {"head": {"sha": "new", "ref": "feature"}},
            {"workflow_runs": []},
            {"workflow_runs": []},
            {"workflow_runs": [{"id": 6, "head_sha": "old", "head_branch": "feature", "status": "completed", "conclusion": "success"}]},
        ]
    )
    result = Controller(None, client=client).check_ci("arthexis/gway", 1348)

    assert result["state"] == "pending"
    assert result["current"] is False
    assert result["stale_runs"] == 1
    assert result["workflows"] == []


def test_check_ci_falls_back_to_provider_state_without_artifact():
    client = FakeClient(
        [
            {"head": {"sha": "abc", "ref": "feature"}},
            {"workflow_runs": [{"id": 7, "name": "python", "head_sha": "abc", "status": "completed", "conclusion": "failure"}]},
            {"workflow_runs": []},
            {"workflow_runs": []},
            {"jobs": [{"id": 11, "name": "Tests", "status": "completed", "conclusion": "failure"}]},
            {"artifacts": []},
        ]
    )
    result = Controller(None, client=client).check_ci("arthexis/gway", 1348)

    assert result["state"] == "failed"
    assert result["failure_kind"] == "infrastructure"
    assert result["result"] is None
    assert result["workflows"][0]["artifact"]["available"] is False


def test_check_ci_does_not_use_passing_artifact_to_classify_other_failure():
    client = FakeClient(
        [
            {"head": {"sha": "abc", "ref": "feature"}},
            {"workflow_runs": [
                {"id": 7, "name": "integration", "head_sha": "abc", "status": "completed", "conclusion": "success"},
                {"id": 8, "name": "secret", "head_sha": "abc", "status": "completed", "conclusion": "failure"},
            ]},
            {"workflow_runs": []},
            {"workflow_runs": []},
            {"jobs": [{"id": 11, "name": "Tests", "status": "completed", "conclusion": "success"}]},
            {"artifacts": [{"id": 22, "name": "gway-ci-result"}]},
            {"jobs": [{"id": 12, "name": "Scan", "status": "completed", "conclusion": "failure"}]},
            {"artifacts": []},
        ],
        artifact=_artifact({"state": "passed", "phase": "tests", "tests": {"failed": 0}}),
    )

    result = Controller(None, client=client).check_ci("arthexis/gway", 1348)

    assert result["state"] == "failed"
    assert result["failure_kind"] == "infrastructure"
    assert result["result"] is None
    assert result["workflows"][0]["result"]["state"] == "passed"
    assert result["workflows"][1]["result"] is None


def test_github_check_ci_is_registered_as_read_only_semantic_operation(gateway):
    assert gateway.operation_routes.expand(
        gateway,
        tokenize("github check ci"),
    ) is True

    operation = gateway.ops.resolve("github.check_ci")
    assert operation is not None
    assert operation.mutates is False
    assert {"github", "source", "read"} <= set(operation.__gway_metadata__["topics"])
