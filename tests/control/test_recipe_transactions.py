import pytest

from gway.dispatch import CheckError, RepeatLimitError
from gway.journal import RollbackError, RollbackRecoveryError, rollback_error_for


def _register_mutation(gateway, source, destination, *, drift=False):
    def mutate():
        if not destination.exists():
            gateway.copy(str(source), to=str(destination), rollback="deploy")
            if drift:
                destination.write_text("external", encoding="utf-8")
        return {"status": "disabled"}

    gateway.mutate = gateway.wrap("mutate", mutate)


def _register_status(gateway, status):
    def read_status():
        return {"status": status}

    gateway.read_status = gateway.wrap("read_status", read_status)


def test_recipe_check_success_commits_named_journal(
    gateway,
    rollback_paths,
    tmp_path,
):
    source, destination = rollback_paths
    _register_mutation(gateway, source, destination)
    _register_status(gateway, "healthy")

    recipe = tmp_path / "deploy.rx"
    recipe.write_text(
        "mutate\nread status\ncheck --status healthy --rollback deploy\ncommit deploy\n",
        encoding="utf-8",
    )

    assert gateway(recipe) == "deploy"
    assert destination.read_text(encoding="utf-8") == "source"
    assert gateway.journal.get("deploy") is None


def test_recipe_check_failure_rolls_back_once_before_boundary(
    gateway,
    rollback_paths,
    tmp_path,
    record_rollbacks,
):
    source, destination = rollback_paths
    _register_mutation(gateway, source, destination)
    _register_status(gateway, "disabled")
    rollbacks = record_rollbacks

    recipe = tmp_path / "deploy.rx"
    recipe.write_text(
        "mutate\nread status\ncheck --status healthy --rollback deploy\n",
        encoding="utf-8",
    )

    with pytest.raises(CheckError):
        gateway(recipe)

    assert rollbacks == ["deploy"]
    assert not destination.exists()
    assert gateway.journal.get("deploy") is None


def test_nested_recipe_shares_journal_with_outer_check(
    gateway,
    rollback_paths,
    tmp_path,
    record_rollbacks,
):
    source, destination = rollback_paths
    _register_mutation(gateway, source, destination)
    _register_status(gateway, "disabled")
    rollbacks = record_rollbacks

    inner = tmp_path / "inner.rx"
    outer = tmp_path / "outer.rx"
    inner.write_text("mutate\n", encoding="utf-8")
    outer.write_text(
        "./inner.rx\nread status\ncheck --status healthy --rollback deploy\n",
        encoding="utf-8",
    )

    with pytest.raises(CheckError):
        gateway(outer)

    assert rollbacks == ["deploy"]
    assert not destination.exists()
    assert gateway.journal.get("deploy") is None


def test_recipe_unless_true_skips_failed_check_and_allows_commit(
    gateway,
    rollback_paths,
    tmp_path,
):
    source, destination = rollback_paths
    _register_mutation(gateway, source, destination)
    _register_status(gateway, "disabled")
    gateway.context["feature_disabled"] = True

    recipe = tmp_path / "optional.rx"
    recipe.write_text(
        "mutate\nread status\n"
        "check --status healthy --unless [feature_disabled] --rollback deploy\n"
        "commit deploy\n",
        encoding="utf-8",
    )

    assert gateway(recipe) == "deploy"
    assert destination.read_text(encoding="utf-8") == "source"
    assert gateway.journal.get("deploy") is None


def test_recipe_repeat_intermediate_failures_do_not_rollback(
    gateway,
    rollback_paths,
    tmp_path,
    record_rollbacks,
):
    source, destination = rollback_paths
    _register_mutation(gateway, source, destination)
    rollbacks = record_rollbacks
    calls = []

    def probe():
        calls.append(len(calls) + 1)
        return len(calls) >= 3

    gateway.probe = gateway.wrap("probe", probe)

    recipe = tmp_path / "repeat-success.rx"
    recipe.write_text(
        "mutate\nprobe\nrepeat --until true --max 5 --rollback deploy\ncommit deploy\n",
        encoding="utf-8",
    )

    assert gateway(recipe) == "deploy"
    assert calls == [1, 2, 3]
    assert rollbacks == []
    assert destination.read_text(encoding="utf-8") == "source"


def test_recipe_repeat_exhaustion_rolls_back_once_before_boundary(
    gateway,
    rollback_paths,
    tmp_path,
    record_rollbacks,
):
    source, destination = rollback_paths
    _register_mutation(gateway, source, destination)
    rollbacks = record_rollbacks

    def probe():
        return False

    gateway.probe = gateway.wrap("probe", probe)

    recipe = tmp_path / "repeat-failure.rx"
    recipe.write_text(
        "mutate\nprobe\nrepeat --until true --max 2 --rollback deploy\n",
        encoding="utf-8",
    )

    with pytest.raises(RepeatLimitError):
        gateway(recipe)

    assert rollbacks == ["deploy"]
    assert not destination.exists()
    assert gateway.journal.get("deploy") is None


def test_recipe_repeat_while_success_preserves_journal_until_commit(
    gateway,
    rollback_paths,
    tmp_path,
    record_rollbacks,
):
    source, destination = rollback_paths
    _register_mutation(gateway, source, destination)
    rollbacks = record_rollbacks
    calls = []

    def pending():
        calls.append(len(calls) + 1)
        return len(calls) < 3

    gateway.pending = gateway.wrap("pending", pending)

    recipe = tmp_path / "repeat-while.rx"
    recipe.write_text(
        "mutate\npending\nrepeat --while true --max 5 --rollback deploy\n"
        "commit deploy\n",
        encoding="utf-8",
    )

    assert gateway(recipe) == "deploy"
    assert calls == [1, 2, 3]
    assert rollbacks == []
    assert destination.read_text(encoding="utf-8") == "source"


def test_incomplete_control_rollback_is_retried_by_boundary_and_keeps_primary(
    gateway,
    rollback_paths,
    tmp_path,
    record_rollbacks,
):
    source, destination = rollback_paths
    _register_mutation(gateway, source, destination, drift=True)
    _register_status(gateway, "disabled")
    rollbacks = record_rollbacks

    recipe = tmp_path / "drift.rx"
    recipe.write_text(
        "mutate\nread status\ncheck --status healthy --rollback deploy\n",
        encoding="utf-8",
    )

    with pytest.raises(CheckError) as raised:
        gateway(recipe)

    recovery = rollback_error_for(raised.value)
    assert isinstance(recovery, RollbackRecoveryError)
    assert len(recovery.errors) == 2
    assert all(isinstance(error, RollbackError) for error in recovery.errors)
    assert recovery.journals == ("deploy", "deploy")
    assert rollbacks == ["deploy", "deploy"]
    assert destination.read_text(encoding="utf-8") == "external"
    assert gateway.journal.require_open("deploy").entries[0].state.value == "applied"
