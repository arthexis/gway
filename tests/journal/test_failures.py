import pytest

from gway.journal import RollbackError, RollbackFailure


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
