from gway.tokens import tokenize
from sampler.github.drive import Controller as DriveController
from tests.github_support import REPOSITORY


class ScriptedDriveController(DriveController):
    def __init__(self, statuses, executions=()):
        super().__init__(None, client=object())
        self.statuses = [dict(status) for status in statuses]
        self.executions = list(executions)
        self.status_calls = 0
        self.action_calls = []

    def _drive_status(self, repository, pull):
        self.status_calls += 1
        if len(self.statuses) > 1:
            return self.statuses.pop(0)
        return dict(self.statuses[0])

    def _execute_drive_action(self, repository, pull, action):
        self.action_calls.append(dict(action))
        if not self.executions:
            return None
        return dict(self.executions.pop(0))


def _status(name, disposition, **extra):
    return {"repository": REPOSITORY, "pr": 10, "status": name, "disposition": disposition, **extra}


def test_terminal_status_returns_done_without_action():
    controller = ScriptedDriveController([_status("certified", "done")])

    result = controller.drive(REPOSITORY, 10)

    assert result == {
        "repository": REPOSITORY,
        "pr": 10,
        "outcome": "done",
        "initial_status": "certified",
        "actions": [],
        "final_status": "certified",
        "disposition": "done",
    }
    assert controller.action_calls == []


def test_wait_returns_resumable_waiting_result():
    controller = ScriptedDriveController([_status("ci-pending", "wait")])

    result = controller.drive(REPOSITORY, 10)

    assert result["outcome"] == "waiting"
    assert result["final_status"] == "ci-pending"
    assert result["actions"] == []


def test_escalation_preserves_diagnostic_target():
    diagnostic = {"kind": "github-ci", "run_id": 30, "job_id": 20}
    controller = ScriptedDriveController([
        _status("ci-failed", "escalate", diagnostic_target=diagnostic)
    ])

    result = controller.drive(REPOSITORY, 10)

    assert result["outcome"] == "escalated"
    assert result["diagnostic_target"] == diagnostic


def test_chunk_one_stops_at_unimplemented_action_boundary():
    action = {"kind": "update-branch", "expected_head_sha": "head"}
    controller = ScriptedDriveController([
        _status("branch-behind", "auto", action=action)
    ])

    result = controller.drive(REPOSITORY, 10)

    assert result["outcome"] == "escalated"
    assert result["reason"] == "drive-action-not-implemented"
    assert result["pending_action"] == action


def test_successful_action_progresses_to_next_fresh_status():
    action = {"kind": "update-branch", "expected_head_sha": "head"}
    controller = ScriptedDriveController(
        [
            _status("branch-behind", "auto", action=action),
            _status("ci-pending", "wait"),
        ],
        executions=[{"kind": "update-branch", "result": "changed"}],
    )

    result = controller.drive(REPOSITORY, 10)

    assert result["outcome"] == "changed"
    assert result["initial_status"] == "branch-behind"
    assert result["final_status"] == "ci-pending"
    assert result["disposition"] == "wait"
    assert result["actions"] == [{"kind": "update-branch", "result": "changed"}]
    assert controller.status_calls == 2


def test_same_status_after_action_trips_no_progress_guard():
    status = _status(
        "branch-behind",
        "auto",
        action={"kind": "update-branch", "expected_head_sha": "head"},
    )
    controller = ScriptedDriveController(
        [status, status],
        executions=[{"kind": "update-branch", "result": "changed"}],
    )

    result = controller.drive(REPOSITORY, 10)

    assert result["outcome"] == "changed"
    assert result["reason"] == "drive-no-progress"


def test_action_budget_stops_reconciliation_before_next_mutation():
    first = _status("first-auto", "auto", action={"kind": "one"})
    second = _status("second-auto", "auto", action={"kind": "two"})
    controller = ScriptedDriveController(
        [first, second],
        executions=[{"kind": "one", "result": "changed"}],
    )

    result = controller.drive(REPOSITORY, 10, max_actions=1)

    assert result["reason"] == "drive-action-budget-exhausted"
    assert result["pending_action"] == {"kind": "two"}
    assert controller.action_calls == [{"kind": "one"}]


def test_drive_is_registered_as_write_capable_semantic_operation(gateway):
    assert gateway.operation_routes.expand(gateway, tokenize("github drive")) is True

    operation = gateway.ops.resolve("github.drive")
    assert operation is not None
    assert operation.mutates is True
    assert {"github", "source", "write"} <= set(operation.__gway_metadata__["topics"])
