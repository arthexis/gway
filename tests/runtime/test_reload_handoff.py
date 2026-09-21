from types import SimpleNamespace

import pytest

from gway import Gateway
from gway.journal import RollbackError, rollback_error_for
from gway.reload import (
    CheckpointState,
    ReloadCheckpoint,
    ReloadHandoffError,
    ReloadStore,
    handoff,
)


class FakeProcess:
    def __init__(self, *, returncode=None):
        self.returncode = returncode
        self.terminated = False
        self.killed = False

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = -15

    def kill(self):
        self.killed = True
        self.returncode = -9

    def wait(self, timeout=None):
        return self.returncode


def _prepared(gateway, *, timeout=0.05):
    return ReloadCheckpoint.create(
        timeout=timeout,
        journal_session_id=gateway.journal.session_id,
        open_journals=gateway.journal.open_names(),
    )


def _mutation(gateway, tmp_path, *, drift=False):
    source = tmp_path / "source.txt"
    destination = tmp_path / "destination.txt"
    source.write_text("source", encoding="utf-8")
    gateway.copy(str(source), to=str(destination), rollback="deploy")
    if drift:
        destination.write_text("external", encoding="utf-8")
    return destination


def test_handoff_launch_failure_rolls_back_in_original_runtime(tmp_path, monkeypatch):
    monkeypatch.setattr("gway.cache.default_root", lambda: tmp_path / "cache")
    gateway = Gateway()
    store = ReloadStore(tmp_path / "reload")

    def fail_popen(argv):
        raise OSError("cannot spawn")

    with pytest.raises(ReloadHandoffError, match="Unable to start"):
        with gateway.execution_scope():
            destination = _mutation(gateway, tmp_path)
            checkpoint = _prepared(gateway)
            handoff(
                gateway,
                checkpoint,
                ["gway"],
                store=store,
                popen=fail_popen,
            )

    assert not destination.exists()
    assert gateway.journal.open_names() == ()
    assert (store.failed / f"{checkpoint.checkpoint_id}.json").is_file()


def test_handoff_timeout_rolls_back_and_stops_unacknowledged_successor(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr("gway.cache.default_root", lambda: tmp_path / "cache")
    gateway = Gateway()
    store = ReloadStore(tmp_path / "reload")
    process = FakeProcess()

    with pytest.raises(ReloadHandoffError, match="did not adopt"):
        with gateway.execution_scope():
            destination = _mutation(gateway, tmp_path)
            checkpoint = _prepared(gateway, timeout=0.001)
            handoff(
                gateway,
                checkpoint,
                ["gway"],
                store=store,
                popen=lambda argv: process,
                poll_interval=0,
            )

    assert process.terminated is True
    assert not destination.exists()
    assert gateway.journal.open_names() == ()


def test_handoff_successor_exit_before_ack_rolls_back(tmp_path, monkeypatch):
    monkeypatch.setattr("gway.cache.default_root", lambda: tmp_path / "cache")
    gateway = Gateway()
    store = ReloadStore(tmp_path / "reload")
    process = FakeProcess(returncode=7)

    with pytest.raises(ReloadHandoffError, match="exited before adoption") as raised:
        with gateway.execution_scope():
            destination = _mutation(gateway, tmp_path)
            checkpoint = _prepared(gateway)
            handoff(
                gateway,
                checkpoint,
                ["gway"],
                store=store,
                popen=lambda argv: process,
            )

    assert raised.value.returncode == 7
    assert not destination.exists()
    assert gateway.journal.open_names() == ()


def test_handoff_waits_for_successor_validation_before_transferring_ownership(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr("gway.cache.default_root", lambda: tmp_path / "cache")
    gateway = Gateway()
    store = ReloadStore(tmp_path / "reload")
    process = FakeProcess()

    def validated_successor(argv):
        checkpoint_id = argv[-1]
        claimed = store.claim(checkpoint_id)
        # Simulate successful runtime/journal restoration before ACK.
        assert claimed.open_journals == ("deploy",)
        store.acknowledge(claimed)
        return process

    with gateway.execution_scope():
        destination = _mutation(gateway, tmp_path)
        checkpoint = _prepared(gateway)
        returned, handoff_checkpoint = handoff(
            gateway,
            checkpoint,
            ["gway"],
            store=store,
            popen=validated_successor,
        )

    assert returned is process
    assert handoff_checkpoint.state is CheckpointState.HANDOFF
    assert destination.read_text(encoding="utf-8") == "source"
    assert gateway.journal.open_names() == ("deploy",)
    assert not store.acknowledgement_path(checkpoint.checkpoint_id).exists()

    gateway.journal.rollback("deploy")
    assert not destination.exists()


def test_successor_validation_failure_before_ack_leaves_parent_rollback_owner(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr("gway.cache.default_root", lambda: tmp_path / "cache")
    gateway = Gateway()
    store = ReloadStore(tmp_path / "reload")
    process = FakeProcess(returncode=2)

    def invalid_successor(argv):
        checkpoint_id = argv[-1]
        claimed = store.claim(checkpoint_id)
        store.quarantine(claimed, RuntimeError("journal mismatch"))
        return process

    with pytest.raises(ReloadHandoffError, match="exited before adoption"):
        with gateway.execution_scope():
            destination = _mutation(gateway, tmp_path)
            checkpoint = _prepared(gateway)
            handoff(
                gateway,
                checkpoint,
                ["gway"],
                store=store,
                popen=invalid_successor,
            )

    assert not destination.exists()
    assert gateway.journal.open_names() == ()


def test_handoff_rollback_failure_attaches_to_reload_error(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr("gway.cache.default_root", lambda: tmp_path / "cache")
    gateway = Gateway()
    store = ReloadStore(tmp_path / "reload")

    def fail_popen(argv):
        raise OSError("cannot spawn")

    with pytest.raises(ReloadHandoffError) as raised:
        with gateway.execution_scope():
            destination = _mutation(gateway, tmp_path, drift=True)
            checkpoint = _prepared(gateway)
            handoff(
                gateway,
                checkpoint,
                ["gway"],
                store=store,
                popen=fail_popen,
            )

    assert destination.read_text(encoding="utf-8") == "external"
    recovery = rollback_error_for(raised.value)
    assert isinstance(recovery, RollbackError)
    assert recovery.journal == "deploy"


def test_ack_survives_fast_successor_completion_until_parent_observes_it(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr("gway.cache.default_root", lambda: tmp_path / "cache")
    gateway = Gateway()
    store = ReloadStore(tmp_path / "reload")
    process = FakeProcess(returncode=0)

    def fast_successor(argv):
        checkpoint_id = argv[-1]
        claimed = store.claim(checkpoint_id)
        adopted = store.acknowledge(claimed)
        store.complete(adopted)
        return process

    with gateway.execution_scope():
        destination = _mutation(gateway, tmp_path)
        checkpoint = _prepared(gateway)
        handoff(
            gateway,
            checkpoint,
            ["gway"],
            store=store,
            popen=fast_successor,
        )

    assert destination.exists()
    assert gateway.journal.open_names() == ("deploy",)
    assert not store.acknowledgement_path(checkpoint.checkpoint_id).exists()
    gateway.journal.rollback("deploy")
