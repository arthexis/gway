import pytest

from gway.dispatch import RepeatLimitError
from gway.journal import JournalError, RollbackError, rollback_error_for


def _counter(gateway, name="probe", *, after=None):
    calls = []

    def operation():
        calls.append(len(calls) + 1)
        if after is not None:
            after(calls)
        return calls[-1]

    setattr(gateway, name, gateway.wrap(name, operation))
    return calls


def test_standalone_repeat_replays_previous_operation(gateway):
    calls = _counter(gateway)

    assert gateway("probe") == 1
    assert gateway("repeat") == 2
    assert calls == [1, 2]


def test_standalone_repeat_times_replays_previous_operation_exactly(gateway):
    calls = _counter(gateway)
    gateway("probe")

    assert gateway("repeat --times 3") == 4
    assert calls == [1, 2, 3, 4]


def test_chained_repeat_replays_entire_current_prefix(gateway):
    calls = []

    def a():
        calls.append("a")
        return "a"

    def b(value):
        calls.append(f"b:{value}")
        return f"{value}b"

    gateway.a = gateway.wrap("a", a)
    gateway.b = gateway.wrap("b", b)

    result = gateway("a - b - repeat --times 2")

    assert result == "ab"
    assert calls == ["a", "b:a", "a", "b:a", "a", "b:a"]


def test_explicit_repeat_target(gateway):
    calls = _counter(gateway)

    assert gateway("repeat probe --times 3") == 3
    assert calls == [1, 2, 3]


def test_repeat_until_operation_gate_receives_latest_result(gateway):
    calls = _counter(gateway)

    def ready(value):
        return value >= 3

    gateway.ready = gateway.wrap("ready", ready)
    gateway("probe")

    assert gateway("repeat --until ready --max 5") == 3
    assert calls == [1, 2, 3]


def test_repeat_while_operation_gate_stops_when_false(gateway):
    calls = _counter(gateway)

    def pending(value):
        return value < 3

    gateway.pending = gateway.wrap("pending", pending)
    gateway("probe")

    assert gateway("repeat --while pending --max 5") == 3
    assert calls == [1, 2, 3]


def test_repeat_until_sigils_are_reresolved_each_iteration(gateway):
    calls = _counter(
        gateway,
        after=lambda values: gateway.context.__setitem__("done", len(values) >= 3),
    )
    gateway.context["done"] = False
    gateway("probe")

    assert gateway("repeat --until [done] --max 5") == 3
    assert calls == [1, 2, 3]


def test_repeat_limit_is_explicit_error(gateway):
    calls = _counter(gateway)

    def never(_value):
        return False

    gateway.never = gateway.wrap("never", never)
    gateway("probe")

    with pytest.raises(RepeatLimitError, match="within 2 attempts"):
        gateway("repeat --until never --max 2")

    assert len(calls) == 3


def test_repeat_gate_rejects_non_boolean_operation_result(gateway):
    def probe():
        return "value"

    def invalid(_value):
        return "yes"

    gateway.probe = gateway.wrap("probe", probe)
    gateway.invalid = gateway.wrap("invalid", invalid)
    gateway("probe")

    with pytest.raises(TypeError, match="must return bool"):
        gateway("repeat --until invalid --max 2")


def test_repeat_defaults_to_one_iteration(gateway):
    calls = _counter(gateway)
    gateway("probe")

    assert gateway("repeat") == 2
    assert calls == [1, 2]


def test_repeat_interval_sleeps_only_between_attempts(gateway, monkeypatch):
    _counter(gateway)
    sleeps = []
    gateway("probe")
    monkeypatch.setattr("gway.dispatch.time.sleep", sleeps.append)

    gateway("repeat --times 3 --interval 0.5")

    assert sleeps == [0.5, 0.5]


def test_repeat_rejects_conflicting_conditions(gateway):
    def probe():
        return True

    gateway.probe = gateway.wrap("probe", probe)
    gateway("probe")

    with pytest.raises(ValueError, match="only one"):
        gateway("repeat --while true --until false")


def test_repeat_without_previous_operation_fails(gateway):
    gateway.execution = None
    gateway.previous_execution = None

    with pytest.raises(LookupError, match="previous operation"):
        gateway("repeat")


def test_repeat_until_true_uses_boolean_replay_result(gateway):
    calls = []

    def probe():
        calls.append(len(calls) + 1)
        return len(calls) >= 3

    gateway.probe = gateway.wrap("probe", probe)
    gateway("probe")

    assert gateway("repeat --until true --max 5") is True
    assert calls == [1, 2, 3]


def test_repeat_until_false_uses_boolean_replay_result(gateway):
    calls = []

    def probe():
        calls.append(len(calls) + 1)
        return len(calls) < 3

    gateway.probe = gateway.wrap("probe", probe)
    gateway("probe")

    assert gateway("repeat --until false --max 5") is False
    assert calls == [1, 2, 3]


def test_repeat_literal_gate_requires_boolean_replay_result(gateway):
    _counter(gateway)
    gateway("probe")

    with pytest.raises(TypeError, match="boolean replay result"):
        gateway("repeat --until true --max 2")


def test_standalone_repeat_replays_previous_statement_in_same_program(gateway):
    calls = _counter(gateway)

    result = gateway("probe ; repeat --times 2")

    assert result == 3
    assert calls == [1, 2, 3]


def test_repeat_limit_rolls_back_named_journal(gateway, tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    destination = tmp_path / "destination.txt"

    def mutate_and_probe():
        if not destination.exists():
            gateway.copy(str(source), to=str(destination), rollback="deploy")
        return False

    gateway.mutate_and_probe = gateway.wrap("mutate_and_probe", mutate_and_probe)

    with pytest.raises(RepeatLimitError) as raised:
        gateway("mutate_and_probe ; repeat --until true --max 2 --rollback deploy")

    assert rollback_error_for(raised.value) is None
    assert not destination.exists()
    assert gateway.journal.get("deploy") is None


def test_successful_repeat_does_not_trigger_rollback(gateway, tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    destination = tmp_path / "destination.txt"
    calls = []

    def mutate_and_probe():
        calls.append(len(calls) + 1)
        if not destination.exists():
            gateway.copy(str(source), to=str(destination), rollback="deploy")
        return len(calls) >= 3

    gateway.mutate_and_probe = gateway.wrap("mutate_and_probe", mutate_and_probe)

    result = gateway(
        "mutate_and_probe ; "
        "repeat --until true --max 5 --rollback deploy ; "
        "commit deploy"
    )

    assert result == "deploy"
    assert destination.read_text(encoding="utf-8") == "source"
    assert gateway.journal.get("deploy") is None


def test_repeat_failure_preserves_primary_when_rollback_is_incomplete(
    gateway,
    tmp_path,
):
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    destination = tmp_path / "destination.txt"

    def mutate_drift_and_probe():
        if not destination.exists():
            gateway.copy(str(source), to=str(destination), rollback="deploy")
            destination.write_text("external", encoding="utf-8")
        return False

    gateway.mutate_drift_and_probe = gateway.wrap(
        "mutate_drift_and_probe",
        mutate_drift_and_probe,
    )

    with pytest.raises(RepeatLimitError) as raised:
        gateway(
            "mutate_drift_and_probe ; repeat --until true --max 1 --rollback deploy"
        )

    recovery = rollback_error_for(raised.value)
    assert isinstance(recovery, RollbackError)
    assert recovery.journal == "deploy"
    assert destination.read_text(encoding="utf-8") == "external"
    assert gateway.journal.require_open("deploy").entries[0].state.value == "applied"


def test_repeat_failure_preserves_missing_journal_as_recovery_context(gateway):
    def probe():
        return False

    gateway.probe = gateway.wrap("probe", probe)
    gateway("probe")

    with pytest.raises(RepeatLimitError) as raised:
        gateway("repeat --until true --max 1 --rollback missing")

    recovery = rollback_error_for(raised.value)
    assert isinstance(recovery, JournalError)
    assert "not open" in str(recovery)


def test_repeat_operation_exception_triggers_rollback(gateway, tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    destination = tmp_path / "destination.txt"

    def mutate():
        gateway.copy(str(source), to=str(destination), rollback="deploy")
        return "ready"

    def fail():
        raise RuntimeError("repeat target failed")

    gateway.mutate = gateway.wrap("mutate", mutate)
    gateway.fail_repeat = gateway.wrap("fail_repeat", fail)

    with pytest.raises(RuntimeError, match="repeat target failed"):
        gateway("mutate ; repeat fail_repeat --times 1 --rollback deploy")

    assert not destination.exists()
    assert gateway.journal.get("deploy") is None
