import pytest

from gway import Gateway
from gway.journal import JournalManager, UncommittedJournalError
from gway.reload import ReloadCheckpoint, ReloadStore


def _checkpoint_for(gateway):
    return ReloadCheckpoint.create(
        journal_session_id=gateway.journal.session_id,
        open_journals=gateway.journal.open_names(),
    )


def test_suspended_execution_preserves_open_journal_for_adoption(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr("gway.cache.default_root", lambda: tmp_path / "cache")
    gateway = Gateway()
    source = tmp_path / "source.txt"
    destination = tmp_path / "destination.txt"
    source.write_text("source", encoding="utf-8")
    store = ReloadStore(tmp_path / "reload")

    with gateway.execution_scope():
        gateway.copy(str(source), to=str(destination), rollback="deploy")
        checkpoint = _checkpoint_for(gateway)
        store.save(checkpoint)
        gateway.suspend_execution(checkpoint)

    assert destination.read_text(encoding="utf-8") == "source"
    assert gateway.journal.open_names() == ("deploy",)

    adopted = JournalManager(
        gateway.journal.root,
        session_id=checkpoint.journal_session_id,
    )
    assert adopted.open_names() == ("deploy",)
    adopted.commit("deploy")
    assert adopted.open_names() == ()


def test_adopted_journal_can_roll_back_after_suspension(tmp_path, monkeypatch):
    monkeypatch.setattr("gway.cache.default_root", lambda: tmp_path / "cache")
    gateway = Gateway()
    source = tmp_path / "source.txt"
    destination = tmp_path / "destination.txt"
    source.write_text("source", encoding="utf-8")
    store = ReloadStore(tmp_path / "reload")

    with gateway.execution_scope():
        gateway.copy(str(source), to=str(destination), rollback="deploy")
        checkpoint = _checkpoint_for(gateway)
        store.save(checkpoint)
        gateway.suspend_execution(checkpoint)

    adopted = JournalManager(
        gateway.journal.root,
        session_id=checkpoint.journal_session_id,
    )
    adopted.rollback("deploy")

    assert not destination.exists()
    assert adopted.open_names() == ()


def test_suspension_preserves_multiple_open_journals_in_order(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr("gway.cache.default_root", lambda: tmp_path / "cache")
    gateway = Gateway()
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first_source = tmp_path / "first-source.txt"
    second_source = tmp_path / "second-source.txt"
    first_source.write_text("first", encoding="utf-8")
    second_source.write_text("second", encoding="utf-8")

    with gateway.execution_scope():
        gateway.copy(str(first_source), to=str(first), rollback="alpha")
        gateway.copy(str(second_source), to=str(second), rollback="beta")
        checkpoint = _checkpoint_for(gateway)
        gateway.suspend_execution(checkpoint)

    assert checkpoint.open_journals == ("alpha", "beta")

    adopted = JournalManager(
        gateway.journal.root,
        session_id=checkpoint.journal_session_id,
    )
    assert adopted.open_names() == ("alpha", "beta")
    adopted.rollback("beta")
    adopted.rollback("alpha")


def test_failed_checkpoint_persistence_leaves_normal_boundary_cleanup(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr("gway.cache.default_root", lambda: tmp_path / "cache")
    gateway = Gateway()
    source = tmp_path / "source.txt"
    destination = tmp_path / "destination.txt"
    source.write_text("source", encoding="utf-8")
    store = ReloadStore(tmp_path / "reload")

    def fail_save(checkpoint):
        raise OSError("checkpoint write failed")

    monkeypatch.setattr(store, "save", fail_save)

    with pytest.raises(OSError, match="checkpoint write failed"):
        with gateway.execution_scope():
            gateway.copy(str(source), to=str(destination), rollback="deploy")
            checkpoint = _checkpoint_for(gateway)
            store.save(checkpoint)
            gateway.suspend_execution(checkpoint)

    assert not destination.exists()
    assert gateway.journal.open_names() == ()


def test_exception_after_suspension_still_rolls_back_open_journals(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr("gway.cache.default_root", lambda: tmp_path / "cache")
    gateway = Gateway()
    source = tmp_path / "source.txt"
    destination = tmp_path / "destination.txt"
    source.write_text("source", encoding="utf-8")

    with pytest.raises(RuntimeError, match="handoff failed"):
        with gateway.execution_scope():
            gateway.copy(str(source), to=str(destination), rollback="deploy")
            checkpoint = _checkpoint_for(gateway)
            gateway.suspend_execution(checkpoint)
            raise RuntimeError("handoff failed")

    assert not destination.exists()
    assert gateway.journal.open_names() == ()


def test_nested_scope_can_suspend_only_outer_boundary_once(tmp_path, monkeypatch):
    monkeypatch.setattr("gway.cache.default_root", lambda: tmp_path / "cache")
    gateway = Gateway()
    source = tmp_path / "source.txt"
    destination = tmp_path / "destination.txt"
    source.write_text("source", encoding="utf-8")

    with gateway.execution_scope():
        gateway.copy(str(source), to=str(destination), rollback="deploy")
        with gateway.execution_scope():
            checkpoint = _checkpoint_for(gateway)
            gateway.suspend_execution(checkpoint)

    assert destination.exists()
    assert gateway.journal.open_names() == ("deploy",)


def test_suspension_rejects_checkpoint_for_other_journal_session(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr("gway.cache.default_root", lambda: tmp_path / "cache")
    gateway = Gateway()

    with gateway.execution_scope():
        checkpoint = ReloadCheckpoint.create(
            journal_session_id="different-session",
            open_journals=(),
        )
        with pytest.raises(ValueError, match="rollback session"):
            gateway.suspend_execution(checkpoint)


def test_suspension_rejects_stale_open_journal_list(tmp_path, monkeypatch):
    monkeypatch.setattr("gway.cache.default_root", lambda: tmp_path / "cache")
    gateway = Gateway()
    source = tmp_path / "source.txt"
    destination = tmp_path / "destination.txt"
    source.write_text("source", encoding="utf-8")

    with pytest.raises(UncommittedJournalError):
        with gateway.execution_scope():
            gateway.copy(str(source), to=str(destination), rollback="deploy")
            checkpoint = ReloadCheckpoint.create(
                journal_session_id=gateway.journal.session_id,
                open_journals=(),
            )
            with pytest.raises(ValueError, match="open journals"):
                gateway.suspend_execution(checkpoint)

    assert not destination.exists()
