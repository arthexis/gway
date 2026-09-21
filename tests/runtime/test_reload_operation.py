import pytest

from gway.reload import (
    CheckpointState,
    ReloadError,
    ReloadHandoffError,
    ReloadTransferred,
)


class FakeSuccessor:
    def poll(self):
        return None


def test_public_reload_transfers_and_old_runtime_does_not_continue(
    gateway,
    tmp_path,
    monkeypatch,
):
    events = []
    captured = {}

    def before():
        events.append("before")
        return "before"

    def after():
        events.append("after")
        return "after"

    gateway.before = gateway.wrap("before", before)
    gateway.after = gateway.wrap("after", after)

    def fake_handoff(runtime, checkpoint, command, *, store=None, **kwargs):
        handoff_checkpoint = checkpoint.transition(CheckpointState.HANDOFF)
        runtime.suspend_execution(handoff_checkpoint)
        captured["checkpoint"] = handoff_checkpoint
        captured["command"] = list(command)
        return FakeSuccessor(), handoff_checkpoint

    monkeypatch.setattr("gway.reload.handoff", fake_handoff)
    monkeypatch.setattr(
        "gway.reload.default_resume_command",
        lambda: ["/managed/bin/gway"],
    )

    recipe = tmp_path / "reload.rx"
    recipe.write_text("before\nreload\nafter\n", encoding="utf-8")

    with pytest.raises(ReloadTransferred) as raised:
        gateway(recipe)

    assert events == ["before"]
    assert captured["command"] == ["/managed/bin/gway"]
    assert captured["checkpoint"].frames[0]["statements"][0][0]["value"] == "after"
    assert raised.value.checkpoint_id == captured["checkpoint"].checkpoint_id


def test_public_reload_timeout_is_captured_and_passed_to_handoff(
    gateway,
    tmp_path,
    monkeypatch,
):
    captured = {}

    def fake_handoff(runtime, checkpoint, command, *, store=None, **kwargs):
        handoff_checkpoint = checkpoint.transition(CheckpointState.HANDOFF)
        runtime.suspend_execution(handoff_checkpoint)
        captured["timeout"] = checkpoint.timeout
        return FakeSuccessor(), handoff_checkpoint

    monkeypatch.setattr("gway.reload.handoff", fake_handoff)
    monkeypatch.setattr("gway.reload.default_resume_command", lambda: ["gway"])

    recipe = tmp_path / "reload.rx"
    recipe.write_text("reload --timeout 7.5\n", encoding="utf-8")

    with pytest.raises(ReloadTransferred):
        gateway(recipe)

    assert captured["timeout"] == 7.5


def test_reload_handoff_failure_rolls_back_and_does_not_run_following_statement(
    gateway,
    rollback_paths,
    tmp_path,
    monkeypatch,
):
    source, destination = rollback_paths
    events = []

    def after():
        events.append("after")
        return "after"

    gateway.after = gateway.wrap("after", after)

    def fail_handoff(runtime, checkpoint, command, *, store=None, **kwargs):
        raise ReloadHandoffError(checkpoint, "handoff failed")

    monkeypatch.setattr("gway.reload.handoff", fail_handoff)
    monkeypatch.setattr("gway.reload.default_resume_command", lambda: ["gway"])

    recipe = tmp_path / "reload-fail.rx"
    recipe.write_text(
        f"copy {source} --to {destination} --rollback deploy\n"
        "reload\n"
        "after\n",
        encoding="utf-8",
    )

    with pytest.raises(ReloadHandoffError, match="handoff failed"):
        gateway(recipe)

    assert events == []
    assert not destination.exists()
    assert gateway.journal.open_names() == ()


def test_reload_transfer_preserves_open_journal_for_successor(
    gateway,
    rollback_paths,
    tmp_path,
    monkeypatch,
):
    source, destination = rollback_paths

    def fake_handoff(runtime, checkpoint, command, *, store=None, **kwargs):
        handoff_checkpoint = checkpoint.transition(CheckpointState.HANDOFF)
        runtime.suspend_execution(handoff_checkpoint)
        return FakeSuccessor(), handoff_checkpoint

    monkeypatch.setattr("gway.reload.handoff", fake_handoff)
    monkeypatch.setattr("gway.reload.default_resume_command", lambda: ["gway"])

    recipe = tmp_path / "reload-journal.rx"
    recipe.write_text(
        f"copy {source} --to {destination} --rollback deploy\n"
        "reload\n"
        "commit deploy\n",
        encoding="utf-8",
    )

    with pytest.raises(ReloadTransferred):
        gateway(recipe)

    assert destination.read_text(encoding="utf-8") == "source"
    assert gateway.journal.open_names() == ("deploy",)
    gateway.journal.rollback("deploy")


def test_reload_requires_active_recipe(gateway):
    with pytest.raises(ReloadError, match="active recipe"):
        gateway("reload")


def test_transfer_signal_without_suspension_cannot_bypass_boundary_rollback(
    gateway,
    rollback_paths,
):
    source, destination = rollback_paths

    with pytest.raises(ReloadTransferred):
        with gateway.execution_scope():
            gateway.copy(str(source), to=str(destination), rollback="deploy")
            raise ReloadTransferred("not-suspended")

    assert not destination.exists()
    assert gateway.journal.open_names() == ()
