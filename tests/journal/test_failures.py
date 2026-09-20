import pytest

from gway.journal import (
    RollbackError,
    RollbackFailure,
    attach_rollback_error,
    rollback_error_for,
)


def test_rollback_failure_preserves_original_exception():
    original = PermissionError("permission denied")
    failure = RollbackFailure(
        journal="deploy",
        sequence=3,
        operation="move",
        error=original,
    )

    assert failure.journal == "deploy"
    assert failure.sequence == 3
    assert failure.operation == "move"
    assert failure.error is original
    assert str(failure) == "entry 3 move: permission denied"


def test_rollback_failure_formats_unknown_operation():
    failure = RollbackFailure(
        journal="deploy",
        sequence=2,
        operation=None,
        error=RuntimeError("restore failed"),
    )

    assert str(failure) == "entry 2 unknown: restore failed"


def test_rollback_error_preserves_failure_records_and_summary():
    first_error = PermissionError("permission denied")
    second_error = RuntimeError("rollback conflict")
    failures = [
        RollbackFailure("deploy", 3, "move", first_error),
        RollbackFailure("deploy", 1, "copy", second_error),
    ]

    error = RollbackError("deploy", failures, attempted=4)

    assert error.journal == "deploy"
    assert error.attempted == 4
    assert error.failures == tuple(failures)
    assert error.failures[0].error is first_error
    assert error.failures[1].error is second_error
    assert str(error) == (
        "Rollback journal 'deploy' incomplete: 2 of 4 entries failed\n"
        "  entry 3 move: permission denied\n"
        "  entry 1 copy: rollback conflict"
    )


def test_rollback_error_can_format_without_attempt_count():
    failure = RollbackFailure(
        "deploy",
        2,
        "render",
        OSError("disk error"),
    )

    error = RollbackError("deploy", [failure])

    assert error.attempted is None
    assert str(error) == (
        "Rollback journal 'deploy' incomplete: 1 entry failed\n"
        "  entry 2 render: disk error"
    )


def test_rollback_error_requires_at_least_one_failure():
    with pytest.raises(ValueError, match="requires at least one failure"):
        RollbackError("deploy", [])


def test_attach_rollback_error_preserves_primary_exception_identity():
    primary = RuntimeError("validation failed")
    rollback_error = RollbackError(
        "deploy",
        [
            RollbackFailure(
                "deploy",
                2,
                "render",
                PermissionError("restore denied"),
            )
        ],
        attempted=2,
    )

    returned = attach_rollback_error(primary, rollback_error)

    assert returned is primary
    assert rollback_error_for(primary) is rollback_error


def test_rollback_error_for_returns_none_without_recovery_failure():
    primary = RuntimeError("validation failed")

    assert rollback_error_for(primary) is None


def test_rollback_after_failure_returns_original_when_recovery_succeeds(
    gateway,
    tmp_path,
):
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    destination = tmp_path / "destination.txt"
    primary = RuntimeError("validation failed")

    gateway.copy(str(source), to=str(destination), rollback="deploy")

    returned = gateway.journal.rollback_after_failure("deploy", primary)

    assert returned is primary
    assert rollback_error_for(primary) is None
    assert gateway.journal.get("deploy") is None
    assert not destination.exists()


def test_rollback_after_failure_attaches_recovery_error_without_replacing_primary(
    gateway,
    tmp_path,
):
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    destination = tmp_path / "destination.txt"
    primary = RuntimeError("validation failed")

    gateway.copy(str(source), to=str(destination), rollback="deploy")
    destination.write_text("external change", encoding="utf-8")

    returned = gateway.journal.rollback_after_failure("deploy", primary)
    recovery = rollback_error_for(primary)

    assert returned is primary
    assert isinstance(recovery, RollbackError)
    assert recovery.failures[0].sequence == 1
    assert gateway.journal.require_open("deploy").entries[0].state.value == "applied"
