import base64
import json

from gway.tokens import tokenize
from sampler.github.rollout import Controller


class RolloutController(Controller):
    def __init__(self, *, merged=True, on_main=True, accepted=True, repository="arthexis/gway"):
        super().__init__(None, client=object())
        self.repository_name = repository
        self.pr_data = {
            "state": "closed" if merged else "open",
            "merged": merged,
            "merge_commit_sha": "merge-sha" if merged else None,
            "head": {"sha": "head-sha"},
            "base": {"ref": "main"},
        }
        self.on_main = on_main
        self.accepted = accepted
        self.issue_state_calls = []

    def pull(self, repository, number):
        return dict(self.pr_data)

    def repository(self, repository):
        return {"default_branch": "main"}

    def branch(self, repository, branch):
        return {"commit": {"sha": "main-sha"}}

    def compare(self, repository, base, head):
        if head == "main-sha":
            return {"status": "ahead" if self.on_main else "diverged"}
        if head == "accepted-sha":
            return {"status": "ahead" if self.accepted else "diverged"}
        return {"status": "diverged"}

    def file(self, repository, path, ref=None):
        manifest = {
            "accepted_at": "2026-09-30T21:24:49+00:00",
            "arthexis_sha": "accepted-sha",
            "gway_sha": "accepted-sha",
            "run_id": "123",
            "run_url": "https://github.com/arthexis/arthexis/actions/runs/123",
            "stages": ["0-gway", "1-arthexis", "2-remote"],
        }
        content = base64.b64encode(json.dumps(manifest).encode()).decode()
        return {"encoding": "base64", "content": content}

    def issue_prs(self, repository, issue, state="open"):
        self.issue_state_calls.append(state)
        return [{"number": 10}]


def test_rollout_reports_open_before_merge():
    controller = RolloutController(merged=False)
    result = controller.check_rollout("arthexis/gway", 10)
    assert result["state"] == "open"
    assert result["merged"]["value"] is False
    assert result["main"]["value"] is False


def test_rollout_distinguishes_stacked_merge_not_on_main():
    controller = RolloutController(on_main=False)
    result = controller.check_rollout("arthexis/gway", 10)
    assert result["state"] == "merged-not-main"
    assert result["merged"]["value"] is True
    assert result["main"]["value"] is False
    assert result["diagnostic_target"]["stage"] == "main"


def test_rollout_reports_on_main_while_watchtower_is_behind():
    controller = RolloutController(accepted=False)
    result = controller.check_rollout("arthexis/gway", 10)
    assert result["state"] == "on-main"
    assert result["main"]["value"] is True
    assert result["watchtower"]["certified"] is False
    assert result["diagnostic_target"]["stage"] == "watchtower"


def test_rollout_certification_accepts_newer_watchtower_revision():
    controller = RolloutController(accepted=True)
    result = controller.check_rollout("arthexis/gway", 10)
    assert result["state"] == "certified"
    assert result["watchtower"]["certified"] is True
    assert result["watchtower"]["accepted_sha"] == "accepted-sha"
    assert result["watchtower"]["required_stage"] == "0-gway"
    assert result["watchtower"]["run_id"] == "123"


def test_arthexis_rollout_requires_arthexis_stage():
    controller = RolloutController(repository="arthexis/arthexis")
    result = controller.check_rollout("arthexis/arthexis", 10)
    assert result["state"] == "certified"
    assert result["watchtower"]["required_stage"] == "1-arthexis"


def test_rollout_issue_targeting_includes_merged_prs():
    controller = RolloutController()
    result = controller.check_rollout("arthexis/gway", issue=1346, serial=True)
    assert result["issue"] == 1346
    assert result["targets"] == [10]
    assert controller.issue_state_calls == ["all"]


def test_observe_rollout_exposes_ancestry_and_manifest():
    controller = RolloutController()
    result = controller.observe_rollout("arthexis/gway", 10)
    assert result["check"]["state"] == "certified"
    assert result["main_compare"]["status"] == "ahead"
    assert result["certification_compare"]["status"] == "ahead"
    assert result["watchtower_manifest"]["gway_sha"] == "accepted-sha"


def test_rollout_operations_are_read_only_semantic_operations(gateway):
    assert gateway.operation_routes.expand(
        gateway,
        tokenize("github check rollout"),
    ) is True
    for name in ("github.check_rollout", "github.observe_rollout"):
        operation = gateway.ops.resolve(name)
        assert operation is not None
        assert operation.mutates is False
        assert {"github", "source", "read"} <= set(
            operation.__gway_metadata__["topics"]
        )
