import pytest

from gway.install.identity import RuntimeIdentity
from gway.recipes import execute_recipe
from gway.reload import (
    CheckpointState,
    ReloadCheckpoint,
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
            checkpoint = ReloadCheckpoint.create()
            raise ReloadTransferred(
                FakeSuccessor(),
                checkpoint,
                gateway.journal.root,
            )

    assert not destination.exists()
    assert gateway.journal.open_names() == ()



def test_reload_when_changed_is_transparent_noop_when_identity_matches(
    gateway,
    tmp_path,
    monkeypatch,
):
    identity = RuntimeIdentity(
        resolved_revision="abc123",
        fingerprint="fp-1",
        scope="user",
    )
    gateway.gway_identity = identity
    events = []

    def after():
        events.append("after")
        return "after"

    gateway.after = gateway.wrap("after", after)
    monkeypatch.setattr(
        "gway.install.identity.managed_gway_identity",
        lambda: identity,
    )

    recipe = tmp_path / "unchanged.rx"
    recipe.write_text("reload --when changed\nafter\n", encoding="utf-8")

    assert gateway(recipe) == "after"
    assert events == ["after"]
    assert gateway._execution_suspension is None


def test_reload_when_changed_transfers_when_revision_differs(
    gateway,
    tmp_path,
    monkeypatch,
):
    source = RuntimeIdentity(
        resolved_revision="abc123",
        fingerprint="fp-1",
        scope="user",
    )
    target = RuntimeIdentity(
        resolved_revision="def456",
        fingerprint="fp-2",
        scope="user",
    )
    gateway.gway_identity = source
    captured = {}

    def fake_handoff(runtime, checkpoint, command, *, store=None, **kwargs):
        handoff_checkpoint = checkpoint.transition(CheckpointState.HANDOFF)
        runtime.suspend_execution(handoff_checkpoint)
        captured["checkpoint"] = handoff_checkpoint
        return FakeSuccessor(), handoff_checkpoint

    monkeypatch.setattr("gway.reload.handoff", fake_handoff)
    monkeypatch.setattr("gway.reload.default_resume_command", lambda: ["gway"])
    monkeypatch.setattr(
        "gway.install.identity.managed_gway_identity",
        lambda: target,
    )

    recipe = tmp_path / "changed.rx"
    recipe.write_text("reload --when changed\n", encoding="utf-8")

    with pytest.raises(ReloadTransferred):
        gateway(recipe)

    checkpoint = captured["checkpoint"]
    assert checkpoint.when == "changed"
    assert checkpoint.source_identity == source.diagnostic()
    assert checkpoint.target_identity == target.diagnostic()


def test_reload_when_changed_reloads_on_same_revision_different_fingerprint(
    gateway,
    tmp_path,
    monkeypatch,
):
    source = RuntimeIdentity(
        resolved_revision="abc123",
        fingerprint="fp-1",
        scope="user",
    )
    target = RuntimeIdentity(
        resolved_revision="abc123",
        fingerprint="fp-2",
        scope="user",
    )
    gateway.gway_identity = source

    def fake_handoff(runtime, checkpoint, command, *, store=None, **kwargs):
        handoff_checkpoint = checkpoint.transition(CheckpointState.HANDOFF)
        runtime.suspend_execution(handoff_checkpoint)
        return FakeSuccessor(), handoff_checkpoint

    monkeypatch.setattr("gway.reload.handoff", fake_handoff)
    monkeypatch.setattr("gway.reload.default_resume_command", lambda: ["gway"])
    monkeypatch.setattr(
        "gway.install.identity.managed_gway_identity",
        lambda: target,
    )

    recipe = tmp_path / "fingerprint-changed.rx"
    recipe.write_text("reload --when changed\n", encoding="utf-8")

    with pytest.raises(ReloadTransferred):
        gateway(recipe)


def test_reload_when_changed_requires_running_identity(gateway, tmp_path):
    gateway.gway_identity = None
    recipe = tmp_path / "missing-running.rx"
    recipe.write_text("reload --when changed\n", encoding="utf-8")

    with pytest.raises(ReloadError, match="running GWAY identity is unavailable"):
        gateway(recipe)


def test_reload_when_changed_requires_installed_identity(
    gateway,
    tmp_path,
    monkeypatch,
):
    gateway.gway_identity = RuntimeIdentity(
        resolved_revision="abc123",
        fingerprint="fp-1",
        scope="user",
    )
    monkeypatch.setattr(
        "gway.install.identity.managed_gway_identity",
        lambda: None,
    )
    recipe = tmp_path / "missing-installed.rx"
    recipe.write_text("reload --when changed\n", encoding="utf-8")

    with pytest.raises(ReloadError, match="installed GWAY identity is unavailable"):
        gateway(recipe)


def test_reload_rejects_unknown_when_condition(gateway, tmp_path):
    recipe = tmp_path / "invalid-when.rx"
    recipe.write_text("reload --when bananas\n", encoding="utf-8")

    with pytest.raises(ReloadError, match="Unknown reload condition"):
        gateway(recipe)



def test_reload_when_changed_noop_leaves_open_journal_for_later_commit(
    gateway,
    rollback_paths,
    tmp_path,
    monkeypatch,
):
    source_file, destination = rollback_paths
    identity = RuntimeIdentity(
        resolved_revision="abc123",
        fingerprint="fp-1",
        scope="user",
    )
    gateway.gway_identity = identity
    monkeypatch.setattr(
        "gway.install.identity.managed_gway_identity",
        lambda: identity,
    )

    recipe = tmp_path / "unchanged-journal.rx"
    recipe.write_text(
        f"copy {source_file} --to {destination} --rollback deploy\n"
        "reload --when changed\n"
        "commit deploy\n",
        encoding="utf-8",
    )

    assert gateway(recipe) == "deploy"
    assert destination.read_text(encoding="utf-8") == "source"
    assert gateway.journal.open_names() == ()



def test_reload_fresh_captures_structural_state_without_semantic_history(
    gateway,
    tmp_path,
    monkeypatch,
):
    captured = {}

    def produce():
        return {"site": "MTY"}

    gateway.produce = gateway.wrap("produce_site", produce)

    def fake_handoff(runtime, checkpoint, command, *, store=None, **kwargs):
        handoff_checkpoint = checkpoint.transition(CheckpointState.HANDOFF)
        runtime.suspend_execution(handoff_checkpoint)
        captured["checkpoint"] = handoff_checkpoint
        return FakeSuccessor(), handoff_checkpoint

    monkeypatch.setattr("gway.reload.handoff", fake_handoff)
    monkeypatch.setattr("gway.reload.default_resume_command", lambda: ["gway"])

    recipe = tmp_path / "fresh.rx"
    recipe.write_text(
        "produce\n"
        "reload --fresh\n"
        "clear\n",
        encoding="utf-8",
    )

    with pytest.raises(ReloadTransferred):
        gateway(recipe)

    checkpoint = captured["checkpoint"]
    assert checkpoint.mode.value == "fresh"
    assert checkpoint.context == {}
    assert checkpoint.result_history == ()
    assert checkpoint.result_subjects == {}
    assert checkpoint.result == {"site": "MTY"}
    assert checkpoint.frames[0]["statements"][0][0]["value"] == "clear"


def test_reload_fresh_when_unchanged_is_transparent_noop(
    gateway,
    tmp_path,
    monkeypatch,
):
    identity = RuntimeIdentity(
        resolved_revision="abc123",
        fingerprint="fp-1",
        scope="user",
    )
    gateway.gway_identity = identity
    gateway.context["site"] = "MTY"
    monkeypatch.setattr(
        "gway.install.identity.managed_gway_identity",
        lambda: identity,
    )

    def show(site):
        return site

    gateway.show = gateway.wrap("show_site", show)

    recipe = tmp_path / "fresh-unchanged.rx"
    recipe.write_text(
        "reload --fresh --when changed\n"
        "show site\n",
        encoding="utf-8",
    )

    assert gateway(recipe) == "MTY"
    assert gateway.context["site"] == "MTY"



def test_reload_restart_rolls_back_open_journals_before_handoff(
    gateway,
    tmp_path,
    monkeypatch,
):
    first_source = tmp_path / "first-source.txt"
    second_source = tmp_path / "second-source.txt"
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first_source.write_text("first", encoding="utf-8")
    second_source.write_text("second", encoding="utf-8")
    order = []
    captured = {}

    original_rollback = gateway.journal.rollback

    def rollback(name):
        order.append(name)
        return original_rollback(name)

    monkeypatch.setattr(gateway.journal, "rollback", rollback)

    def fake_handoff(runtime, checkpoint, command, *, store=None, **kwargs):
        captured["checkpoint"] = checkpoint
        handoff_checkpoint = checkpoint.transition(CheckpointState.HANDOFF)
        runtime.suspend_execution(handoff_checkpoint)
        return FakeSuccessor(), handoff_checkpoint

    monkeypatch.setattr("gway.reload.handoff", fake_handoff)
    monkeypatch.setattr("gway.reload.default_resume_command", lambda: ["gway"])

    recipe = tmp_path / "restart.rx"
    recipe.write_text(
        f"copy {first_source} --to {first} --rollback alpha\n"
        f"copy {second_source} --to {second} --rollback beta\n"
        "reload --restart\n",
        encoding="utf-8",
    )

    with pytest.raises(ReloadTransferred):
        gateway(recipe)

    assert order == ["beta", "alpha"]
    assert not first.exists()
    assert not second.exists()
    checkpoint = captured["checkpoint"]
    assert checkpoint.mode.value == "restart"
    assert checkpoint.open_journals == ()
    assert checkpoint.journal_session_id is None
    assert checkpoint.context == {}
    assert checkpoint.result_history == ()
    assert checkpoint.result_subjects == {}


def test_reload_restart_rollback_failure_prevents_handoff(
    gateway,
    rollback_paths,
    tmp_path,
    monkeypatch,
):
    source, destination = rollback_paths
    called = []

    def fail_rollback(name):
        raise RuntimeError("rollback failed")

    def forbidden_handoff(*args, **kwargs):
        called.append(True)
        raise AssertionError("handoff must not run after rollback failure")

    monkeypatch.setattr(gateway.journal, "rollback", fail_rollback)
    monkeypatch.setattr("gway.reload.handoff", forbidden_handoff)

    recipe = tmp_path / "restart-fail.rx"
    recipe.write_text(
        f"copy {source} --to {destination} --rollback deploy\n"
        "reload --restart\n",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="rollback failed"):
        gateway(recipe)

    assert called == []


def test_reload_restart_from_nested_recipe_targets_top_level_invocation(
    gateway,
    tmp_path,
    monkeypatch,
):
    captured = {}

    def fake_handoff(runtime, checkpoint, command, *, store=None, **kwargs):
        captured["checkpoint"] = checkpoint
        handoff_checkpoint = checkpoint.transition(CheckpointState.HANDOFF)
        runtime.suspend_execution(handoff_checkpoint)
        return FakeSuccessor(), handoff_checkpoint

    monkeypatch.setattr("gway.reload.handoff", fake_handoff)
    monkeypatch.setattr("gway.reload.default_resume_command", lambda: ["gway"])

    outer = tmp_path / "outer.rx"
    inner = tmp_path / "inner.rx"
    outer.write_text("./inner.rx\n", encoding="utf-8")
    inner.write_text("reload --restart\n", encoding="utf-8")

    with pytest.raises(ReloadTransferred):
        execute_recipe(gateway, outer, context={"site": "MTY"})

    frame = captured["checkpoint"].frames[0]
    assert frame["recipe"] == str(outer.resolve())
    assert frame["context"] == {"site": "MTY"}


def test_reload_restart_when_unchanged_does_not_rollback(
    gateway,
    rollback_paths,
    tmp_path,
    monkeypatch,
):
    source, destination = rollback_paths
    identity = RuntimeIdentity(
        resolved_revision="abc123",
        fingerprint="fp-1",
        scope="user",
    )
    gateway.gway_identity = identity
    monkeypatch.setattr(
        "gway.install.identity.managed_gway_identity",
        lambda: identity,
    )
    rollbacks = []
    original = gateway.journal.rollback

    def rollback(name):
        rollbacks.append(name)
        return original(name)

    monkeypatch.setattr(gateway.journal, "rollback", rollback)

    recipe = tmp_path / "restart-unchanged.rx"
    recipe.write_text(
        f"copy {source} --to {destination} --rollback deploy\n"
        "reload --restart --when changed\n"
        "commit deploy\n",
        encoding="utf-8",
    )

    assert gateway(recipe) == "deploy"
    assert rollbacks == []
    assert destination.exists()


def test_reload_fresh_and_restart_are_rejected_before_rollback(
    gateway,
    rollback_paths,
    tmp_path,
    monkeypatch,
):
    source, destination = rollback_paths
    rollbacks = []
    original = gateway.journal.rollback

    def rollback(name):
        rollbacks.append(name)
        return original(name)

    monkeypatch.setattr(gateway.journal, "rollback", rollback)

    recipe = tmp_path / "invalid-modes.rx"
    recipe.write_text(
        f"copy {source} --to {destination} --rollback deploy\n"
        "reload --fresh --restart\n",
        encoding="utf-8",
    )

    with pytest.raises(ReloadError, match="mutually exclusive"):
        gateway(recipe)

    assert rollbacks == ["deploy"]
    assert not destination.exists()
