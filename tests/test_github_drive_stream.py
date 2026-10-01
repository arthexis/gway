from sampler.github.drive import Controller as DriveController
from tests.github_support import REPOSITORY


class StreamDriveController(DriveController):
    def __init__(self, passes, statuses):
        super().__init__(None, client=object())
        self.passes = [dict(result) for result in passes]
        self.statuses = [dict(status) for status in statuses]
        self.action_offsets = []

    def _drive_once(
        self,
        repository,
        pull,
        *,
        max_actions=8,
        mutate=True,
        action_offset=0,
    ):
        self.action_offsets.append(action_offset)
        if not self.passes:
            raise AssertionError("unexpected reconciliation pass")
        return self.passes.pop(0)

    def _drive_status(self, repository, pull):
        if len(self.statuses) > 1:
            return self.statuses.pop(0)
        return dict(self.statuses[0])


def _status(name, disposition, **extra):
    return {
        "repository": REPOSITORY,
        "pr": 10,
        "status": name,
        "disposition": disposition,
        **extra,
    }


def _result(outcome, final_status, disposition, actions=(), **extra):
    return {
        "repository": REPOSITORY,
        "pr": 10,
        "outcome": outcome,
        "initial_status": final_status,
        "actions": list(actions),
        "final_status": final_status,
        "disposition": disposition,
        **extra,
    }


def test_stream_continues_across_wait_and_finishes_on_done():
    controller = StreamDriveController(
        passes=[
            _result("waiting", "ci-pending", "wait"),
            _result("done", "certified", "done"),
        ],
        statuses=[
            _status("ci-pending", "wait"),
            _status("ci-pending", "wait"),
            _status("certified", "done"),
            _status("certified", "done"),
        ],
    )

    events = list(controller.drive(REPOSITORY, 10, stream=True, interval=0))

    assert [event["event"] for event in events] == [
        "status",
        "transition",
        "status",
        "terminal",
    ]
    assert events[0]["status"] == "ci-pending"
    assert events[1]["before"] == "ci-pending"
    assert events[1]["after"] == "certified"
    assert events[-1]["outcome"] == "done"
    assert events[-1]["terminal"] is True


def test_stream_emits_actions_and_preserves_changed_state_until_timeout():
    action = {"kind": "update-branch", "result": "changed"}
    controller = StreamDriveController(
        passes=[_result("changed", "ci-pending", "wait", actions=[action])],
        statuses=[_status("ci-pending", "wait")],
    )

    events = list(
        controller.drive(
            REPOSITORY,
            10,
            stream=True,
            interval=0,
            timeout=0,
        )
    )

    assert [event["event"] for event in events] == ["action", "status", "timeout"]
    assert events[0]["action"] == action
    assert events[-1]["changed"] is True
    assert events[-1]["terminal"] is True


def test_stream_stops_on_escalation_with_diagnostic_target():
    diagnostic = {"kind": "github-ci", "run_id": 30, "job_id": 20}
    controller = StreamDriveController(
        passes=[_result("escalated", "ci-failed", "escalate")],
        statuses=[_status("ci-failed", "escalate", diagnostic_target=diagnostic)],
    )

    events = list(controller.drive(REPOSITORY, 10, stream=True, interval=0))

    assert [event["event"] for event in events] == ["status", "terminal"]
    assert events[-1]["outcome"] == "escalated"
    assert events[-1]["diagnostic_target"] == diagnostic


def test_stream_carries_total_action_count_into_later_reconciliation_passes():
    first_action = {"kind": "update-branch", "result": "changed"}
    second_action = {"kind": "ensure-auto-merge", "result": "changed"}
    controller = StreamDriveController(
        passes=[
            _result("changed", "ci-pending", "wait", actions=[first_action]),
            _result("changed", "certified", "done", actions=[second_action]),
        ],
        statuses=[
            _status("ci-pending", "wait"),
            _status("certified", "done"),
            _status("certified", "done"),
        ],
    )

    events = list(controller.drive(REPOSITORY, 10, stream=True, interval=0, max_actions=2))

    assert controller.action_offsets == [0, 1]
    assert [event["action"]["kind"] for event in events if event["event"] == "action"] == [
        "update-branch",
        "ensure-auto-merge",
    ]
    assert events[-1]["event"] == "terminal"
    assert events[-1]["changed"] is True


def test_stream_reason_is_a_terminal_escalation_even_when_boundary_is_auto():
    pending = {"kind": "merge-pull", "expected_head_sha": "head"}
    controller = StreamDriveController(
        passes=[
            _result(
                "escalated",
                "merge-ready",
                "auto",
                reason="drive-action-budget-exhausted",
                pending_action=pending,
            )
        ],
        statuses=[_status("merge-ready", "auto", action=pending)],
    )

    events = list(controller.drive(REPOSITORY, 10, stream=True, interval=0))

    assert events[-1]["event"] == "terminal"
    assert events[-1]["outcome"] == "escalated"
    assert events[-1]["reason"] == "drive-action-budget-exhausted"
    assert events[-1]["pending_action"] == pending


def test_stream_rejects_negative_interval_and_timeout():
    controller = StreamDriveController([], [_status("ci-pending", "wait")])

    try:
        controller.drive(REPOSITORY, 10, stream=True, interval=-1)
    except ValueError as exc:
        assert "interval" in str(exc)
    else:
        raise AssertionError("negative stream interval was accepted")

    try:
        controller.drive(REPOSITORY, 10, stream=True, timeout=-1)
    except ValueError as exc:
        assert "timeout" in str(exc)
    else:
        raise AssertionError("negative stream timeout was accepted")
