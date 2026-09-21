import pytest

from gway import Gateway
from gway.journal import RollbackError, rollback_error_for
from gway.reload import (
    ReloadCheckpoint,
    ReloadSuccessorError,
    supervise_successor,
)


class FinishedProcess:
    def __init__(self, returncode):
        self.returncode = returncode

    def wait(self):
        return self.returncode


def _checkpoint(gateway, *, mode="continue"):
    return ReloadCheckpoint.create(
        mode=mode,
        journal_session_id=(
            None if mode == "restart" else gateway.journal.session_id
        ),
        open_journals=(
            () if mode == "restart" else gateway.journal.open_names()
        ),
    )


def _mutation(gateway, tmp_path, name, journal):
    source = tmp_path / f"{name}-source.txt"
    destination = tmp_path / f"{name}.txt"
    source.write_text(name, encoding="utf-8")
    gateway.copy(str(source), to=str(destination), rollback=journal)
    return destination


def test_supervisor_success_exit_does_not_rollback(tmp_path, monkeypatch):
    monkeypatch.setattr("gway.cache.default_root", lambda: tmp_path / "cache")
    gateway = Gateway()
    destination = _mutation(gateway, tmp_path, "value", "deploy")
    checkpoint = _checkpoint(gateway)

    assert supervise_successor(
        FinishedProcess(0),
        checkpoint,
        gateway.journal.root,
    ) == 0

    assert destination.exists()
    assert gateway.journal.open_names() == ("deploy",)
    gateway.journal.rollback("deploy")


def test_supervisor_abnormal_exit_rolls_back_still_open_journals(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr("gway.cache.default_root", lambda: tmp_path / "cache")
    gateway = Gateway()
    destination = _mutation(gateway, tmp_path, "value", "deploy")
    checkpoint = _checkpoint(gateway)

    with pytest.raises(ReloadSuccessorError) as raised:
        supervise_successor(
            FinishedProcess(-9),
            checkpoint,
            gateway.journal.root,
        )

    assert raised.value.returncode == -9
    assert raised.value.recovered_journals == ("deploy",)
    assert not destination.exists()


def test_supervisor_does_not_resurrect_committed_journal(tmp_path, monkeypatch):
    monkeypatch.setattr("gway.cache.default_root", lambda: tmp_path / "cache")
    gateway = Gateway()
    destination = _mutation(gateway, tmp_path, "value", "deploy")
    checkpoint = _checkpoint(gateway)

    gateway.journal.commit("deploy")

    with pytest.raises(ReloadSuccessorError) as raised:
        supervise_successor(
            FinishedProcess(4),
            checkpoint,
            gateway.journal.root,
        )

    assert raised.value.recovered_journals == ()
    assert destination.exists()


def test_supervisor_rolls_back_remaining_journals_newest_first(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr("gway.cache.default_root", lambda: tmp_path / "cache")
    gateway = Gateway()
    first = _mutation(gateway, tmp_path, "first", "alpha")
    second = _mutation(gateway, tmp_path, "second", "beta")
    checkpoint = _checkpoint(gateway)
    observed = []

    from gway.journal import JournalManager

    original = JournalManager.rollback

    def rollback(self, name):
        observed.append(name)
        return original(self, name)

    monkeypatch.setattr(JournalManager, "rollback", rollback)

    with pytest.raises(ReloadSuccessorError):
        supervise_successor(
            FinishedProcess(3),
            checkpoint,
            gateway.journal.root,
        )

    assert observed == ["beta", "alpha"]
    assert not first.exists()
    assert not second.exists()


def test_supervisor_attaches_rollback_failure_to_successor_error(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr("gway.cache.default_root", lambda: tmp_path / "cache")
    gateway = Gateway()
    destination = _mutation(gateway, tmp_path, "value", "deploy")
    destination.write_text("external", encoding="utf-8")
    checkpoint = _checkpoint(gateway)

    with pytest.raises(ReloadSuccessorError) as raised:
        supervise_successor(
            FinishedProcess(2),
            checkpoint,
            gateway.journal.root,
        )

    recovery = rollback_error_for(raised.value)
    assert isinstance(recovery, RollbackError)
    assert recovery.journal == "deploy"
    assert destination.read_text(encoding="utf-8") == "external"


def test_restart_supervision_never_recovers_abandoned_session(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr("gway.cache.default_root", lambda: tmp_path / "cache")
    gateway = Gateway()
    checkpoint = _checkpoint(gateway, mode="restart")

    from gway import reload as reload_module

    called = []

    def forbidden(*args, **kwargs):
        called.append(True)
        raise AssertionError("restart supervision must not recover old journals")

    monkeypatch.setattr(reload_module, "recover_adopted_journals", forbidden)

    with pytest.raises(ReloadSuccessorError):
        supervise_successor(
            FinishedProcess(1),
            checkpoint,
            gateway.journal.root,
        )

    assert called == []
