import logging

import pytest

from gway.journal import (
    JournalError,
    RollbackError,
    RollbackRecoveryError,
    UncommittedJournalError,
    rollback_error_for,
)
from gway.recipes import execute_recipe


def _record_finalization(gateway, monkeypatch):
    calls = []

    def finalize(primary=None):
        calls.append((gateway.execution_depth, primary))

    monkeypatch.setattr(gateway, "_finalize_execution", finalize)
    return calls


def test_dispatch_finalizes_once_at_outer_boundary(gateway, monkeypatch):
    calls = _record_finalization(gateway, monkeypatch)

    result = gateway(["env", "PATH"])

    assert result is not None
    assert calls == [(0, None)]
    assert gateway.execution_depth == 0


def test_nested_dispatch_does_not_finalize_inner_call(gateway, monkeypatch):
    calls = _record_finalization(gateway, monkeypatch)
    depths = []

    def nested():
        depths.append(gateway.execution_depth)
        result = gateway(["env", "PATH"])
        depths.append(gateway.execution_depth)
        return result

    gateway.nested = gateway.wrap("nested", nested)

    result = gateway(["nested"])

    assert result is not None
    assert depths == [1, 1]
    assert calls == [(0, None)]


def test_nested_dispatch_can_share_open_journal_until_outer_program_commits(
    gateway,
    tmp_path,
    monkeypatch,
):
    calls = _record_finalization(gateway, monkeypatch)
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    destination = tmp_path / "destination.txt"

    def nested():
        gateway.copy(str(source), to=str(destination), rollback="deploy")
        return "nested"

    gateway.nested = gateway.wrap("nested", nested)

    gateway("nested ; commit deploy")

    assert destination.read_text(encoding="utf-8") == "source"
    assert gateway.journal.get("deploy") is None
    assert calls == [(0, None)]


def test_recipe_execution_uses_same_outer_boundary(gateway, tmp_path, monkeypatch):
    calls = _record_finalization(gateway, monkeypatch)
    recipe = tmp_path / "nested.rx"
    recipe.write_text("env PATH\n", encoding="utf-8")

    result = gateway([recipe])

    assert result is not None
    assert calls == [(0, None)]


def test_direct_recipe_execution_owns_boundary(gateway, tmp_path, monkeypatch):
    calls = _record_finalization(gateway, monkeypatch)
    recipe = tmp_path / "direct.rx"
    recipe.write_text("env PATH\n", encoding="utf-8")

    _, result = execute_recipe(gateway, recipe)

    assert result is not None
    assert calls == [(0, None)]


def test_chain_holds_outer_scope_until_context_exit(gateway, monkeypatch):
    calls = _record_finalization(gateway, monkeypatch)

    with gateway.chain("env PATH") as chain:
        assert gateway.execution_depth == 1
        assert calls == []
        chain("env HOME")
        assert gateway.execution_depth == 1
        assert calls == []

    assert gateway.execution_depth == 0
    assert calls == [(0, None)]


def test_outer_boundary_receives_primary_exception(gateway, monkeypatch):
    calls = _record_finalization(gateway, monkeypatch)
    primary = RuntimeError("boom")

    def fail():
        raise primary

    gateway.fail_boundary = gateway.wrap("fail_boundary", fail)

    with pytest.raises(RuntimeError) as raised:
        gateway(["fail_boundary"])

    assert raised.value is primary
    assert calls == [(0, primary)]
    assert gateway.execution_depth == 0


def test_chain_failure_finalizes_once_with_primary(gateway, monkeypatch):
    calls = _record_finalization(gateway, monkeypatch)
    primary = RuntimeError("chain failed")

    def fail(*args):
        raise primary

    gateway.fail_chain = gateway.wrap("fail_chain", fail)

    with pytest.raises(RuntimeError) as raised:
        with gateway.chain("env PATH") as chain:
            chain("fail_chain")

    assert raised.value is primary
    assert calls == [(0, primary)]
    assert gateway.execution_depth == 0


def test_successful_execution_with_open_journal_auto_rolls_back_and_fails(
    gateway,
    tmp_path,
):
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    destination = tmp_path / "destination.txt"

    with pytest.raises(UncommittedJournalError) as raised:
        gateway(
            [
                "copy",
                str(source),
                "--to",
                str(destination),
                "--rollback",
                "deploy",
            ]
        )

    assert raised.value.journals == ("deploy",)
    assert raised.value.rollback_errors == ()
    assert not destination.exists()
    assert gateway.journal.get("deploy") is None
    assert gateway.execution_depth == 0


def test_prepared_only_journal_is_closed_but_still_fails_boundary(
    gateway,
):
    def prepare_only():
        gateway.journal.prepare("deploy")
        return "prepared"

    gateway.prepare_only = gateway.wrap("prepare_only", prepare_only)

    with pytest.raises(UncommittedJournalError) as raised:
        gateway(["prepare_only"])

    assert raised.value.journals == ("deploy",)
    assert gateway.journal.get("deploy") is None


def test_chain_leaked_journal_rolls_back_on_context_exit(
    gateway,
    tmp_path,
):
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    destination = tmp_path / "destination.txt"

    with pytest.raises(UncommittedJournalError):
        with gateway.chain("env PATH"):
            gateway.copy(
                str(source),
                to=str(destination),
                rollback="deploy",
            )
            assert destination.exists()

    assert not destination.exists()
    assert gateway.journal.get("deploy") is None
    assert gateway.execution_depth == 0


def test_incomplete_boundary_rollback_keeps_protocol_error_primary(
    gateway,
    tmp_path,
):
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    destination = tmp_path / "destination.txt"

    def leak_with_drift():
        gateway.copy(str(source), to=str(destination), rollback="deploy")
        destination.write_text("external change", encoding="utf-8")
        return "done"

    gateway.leak_with_drift = gateway.wrap("leak_with_drift", leak_with_drift)

    with pytest.raises(UncommittedJournalError) as raised:
        gateway(["leak_with_drift"])

    error = raised.value
    assert error.journals == ("deploy",)
    assert len(error.rollback_errors) == 1
    assert isinstance(error.rollback_errors[0], RollbackError)
    assert error.__cause__ is error.rollback_errors[0]
    assert destination.read_text(encoding="utf-8") == "external change"
    assert gateway.journal.require_open("deploy").entries[0].state.value == "applied"


def test_uncommitted_boundary_detection_logs_at_info(
    gateway,
    tmp_path,
    caplog,
):
    caplog.set_level(logging.INFO, logger="gway")
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    destination = tmp_path / "destination.txt"

    with pytest.raises(UncommittedJournalError):
        gateway(
            [
                "copy",
                str(source),
                "--to",
                str(destination),
                "--rollback",
                "deploy",
            ]
        )

    messages = [record.getMessage() for record in caplog.records]
    assert (
        "uncommitted rollback journal 'deploy' detected at execution boundary"
        in messages
    )
    assert "rolling back journal 'deploy'" in messages
    assert "rolled back journal 'deploy'" in messages


def test_failed_execution_auto_rolls_back_and_preserves_primary(
    gateway,
    tmp_path,
):
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    destination = tmp_path / "destination.txt"
    primary = RuntimeError("validation failed")

    def fail_after_mutation():
        gateway.copy(str(source), to=str(destination), rollback="deploy")
        raise primary

    gateway.fail_after_mutation = gateway.wrap(
        "fail_after_mutation",
        fail_after_mutation,
    )

    with pytest.raises(RuntimeError) as raised:
        gateway(["fail_after_mutation"])

    assert raised.value is primary
    assert rollback_error_for(primary) is None
    assert not destination.exists()
    assert gateway.journal.get("deploy") is None
    assert gateway.execution_depth == 0


def test_failed_execution_with_incomplete_recovery_keeps_primary(
    gateway,
    tmp_path,
):
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    destination = tmp_path / "destination.txt"
    primary = RuntimeError("validation failed")

    def fail_after_drift():
        gateway.copy(str(source), to=str(destination), rollback="deploy")
        destination.write_text("external change", encoding="utf-8")
        raise primary

    gateway.fail_after_drift = gateway.wrap(
        "fail_after_drift",
        fail_after_drift,
    )

    with pytest.raises(RuntimeError) as raised:
        gateway(["fail_after_drift"])

    assert raised.value is primary
    recovery = rollback_error_for(primary)
    assert isinstance(recovery, RollbackError)
    assert recovery.failures[0].sequence == 1
    assert destination.read_text(encoding="utf-8") == "external change"
    assert gateway.journal.require_open("deploy").entries[0].state.value == "applied"
    assert gateway.execution_depth == 0


def test_failed_execution_closes_prepared_only_journal(
    gateway,
):
    primary = RuntimeError("prepare failed")

    def prepare_then_fail():
        gateway.journal.prepare("deploy")
        raise primary

    gateway.prepare_then_fail = gateway.wrap(
        "prepare_then_fail",
        prepare_then_fail,
    )

    with pytest.raises(RuntimeError) as raised:
        gateway(["prepare_then_fail"])

    assert raised.value is primary
    assert rollback_error_for(primary) is None
    assert gateway.journal.get("deploy") is None


def test_failed_execution_boundary_logs_automatic_recovery(
    gateway,
    tmp_path,
    caplog,
):
    caplog.set_level(logging.INFO, logger="gway")
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    destination = tmp_path / "destination.txt"
    primary = RuntimeError("validation failed")

    def fail_after_mutation():
        gateway.copy(str(source), to=str(destination), rollback="deploy")
        raise primary

    gateway.fail_after_mutation_log = gateway.wrap(
        "fail_after_mutation_log",
        fail_after_mutation,
    )

    with pytest.raises(RuntimeError):
        gateway(["fail_after_mutation_log"])

    messages = [record.getMessage() for record in caplog.records]
    assert (
        "execution failed with open rollback journal 'deploy'; "
        "rolling back automatically" in messages
    )
    assert "rolling back journal 'deploy'" in messages
    assert "rolled back journal 'deploy'" in messages


def test_success_boundary_rolls_back_multiple_journals_in_reverse_open_order(
    gateway,
    tmp_path,
    record_rollbacks,
):
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"

    def leak_two():
        gateway.copy(str(source), to=str(first), rollback="alpha")
        gateway.copy(str(source), to=str(second), rollback="beta")
        return "done"

    gateway.leak_two = gateway.wrap("leak_two", leak_two)

    with pytest.raises(UncommittedJournalError) as raised:
        gateway(["leak_two"])

    assert raised.value.journals == ("alpha", "beta")
    assert raised.value.rollback_errors == ()
    assert record_rollbacks == ["beta", "alpha"]
    assert not first.exists()
    assert not second.exists()
    assert gateway.journal.open_names() == ()


def test_success_boundary_attempts_all_journals_when_one_rollback_fails(
    gateway,
    tmp_path,
):
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"

    def leak_two_with_drift():
        gateway.copy(str(source), to=str(first), rollback="alpha")
        gateway.copy(str(source), to=str(second), rollback="beta")
        first.write_text("external alpha", encoding="utf-8")
        return "done"

    gateway.leak_two_with_drift = gateway.wrap(
        "leak_two_with_drift",
        leak_two_with_drift,
    )

    with pytest.raises(UncommittedJournalError) as raised:
        gateway(["leak_two_with_drift"])

    error = raised.value
    assert error.journals == ("alpha", "beta")
    assert len(error.rollback_errors) == 1
    assert error.rollback_errors[0].journal == "alpha"
    assert gateway.journal.open_names() == ("alpha",)
    assert first.read_text(encoding="utf-8") == "external alpha"
    assert not second.exists()


def test_failed_execution_aggregates_recovery_failures_across_journals(
    gateway,
    tmp_path,
):
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    primary = RuntimeError("forward failed")

    def fail_with_two_drifted_journals():
        gateway.copy(str(source), to=str(first), rollback="alpha")
        gateway.copy(str(source), to=str(second), rollback="beta")
        first.write_text("external alpha", encoding="utf-8")
        second.write_text("external beta", encoding="utf-8")
        raise primary

    gateway.fail_with_two_drifted_journals = gateway.wrap(
        "fail_with_two_drifted_journals",
        fail_with_two_drifted_journals,
    )

    with pytest.raises(RuntimeError) as raised:
        gateway(["fail_with_two_drifted_journals"])

    assert raised.value is primary
    recovery = rollback_error_for(primary)
    assert isinstance(recovery, RollbackRecoveryError)
    assert recovery.journals == ("beta", "alpha")
    assert [error.journal for error in recovery.errors] == ["beta", "alpha"]
    assert gateway.journal.open_names() == ("alpha", "beta")
    assert first.read_text(encoding="utf-8") == "external alpha"
    assert second.read_text(encoding="utf-8") == "external beta"


def test_failed_execution_recovers_all_journals_even_if_one_fails(
    gateway,
    tmp_path,
):
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    primary = RuntimeError("forward failed")

    def fail_with_one_drift():
        gateway.copy(str(source), to=str(first), rollback="alpha")
        gateway.copy(str(source), to=str(second), rollback="beta")
        first.write_text("external alpha", encoding="utf-8")
        raise primary

    gateway.fail_with_one_drift = gateway.wrap(
        "fail_with_one_drift",
        fail_with_one_drift,
    )

    with pytest.raises(RuntimeError) as raised:
        gateway(["fail_with_one_drift"])

    assert raised.value is primary
    recovery = rollback_error_for(primary)
    assert isinstance(recovery, RollbackError)
    assert recovery.journal == "alpha"
    assert gateway.journal.open_names() == ("alpha",)
    assert first.read_text(encoding="utf-8") == "external alpha"
    assert not second.exists()


def test_multi_journal_boundary_logs_follow_reverse_open_order(
    gateway,
    tmp_path,
    caplog,
):
    caplog.set_level(logging.INFO, logger="gway")
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"

    def leak_two():
        gateway.copy(str(source), to=str(first), rollback="alpha")
        gateway.copy(str(source), to=str(second), rollback="beta")
        return "done"

    gateway.leak_two_for_logs = gateway.wrap(
        "leak_two_for_logs",
        leak_two,
    )

    with pytest.raises(UncommittedJournalError):
        gateway(["leak_two_for_logs"])

    boundary_messages = [
        record.getMessage()
        for record in caplog.records
        if "detected at execution boundary" in record.getMessage()
    ]
    assert boundary_messages == [
        "uncommitted rollback journal 'beta' detected at execution boundary",
        "uncommitted rollback journal 'alpha' detected at execution boundary",
    ]


def test_failed_boundary_preserves_primary_for_nonaggregate_journal_error(
    gateway,
    monkeypatch,
):
    primary = RuntimeError("forward failed")
    gateway.journal.prepare("deploy")

    def fail_rollback(name):
        raise JournalError(f"cannot recover {name}")

    monkeypatch.setattr(gateway.journal, "rollback", fail_rollback)

    def fail():
        raise primary

    gateway.fail_with_journal_error = gateway.wrap("fail_with_journal_error", fail)

    with pytest.raises(RuntimeError) as raised:
        gateway(["fail_with_journal_error"])

    assert raised.value is primary
    recovery = rollback_error_for(primary)
    assert isinstance(recovery, JournalError)
    assert "cannot recover deploy" in str(recovery)
