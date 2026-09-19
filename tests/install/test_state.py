import sqlite3

import pytest

from gway.install import Installation, InstallState


def _record(tmp_path, **values):
    data = {
        "name": "wire",
        "source": "arthexis/gway-wire",
        "install_path": tmp_path / "projects" / "wire",
        "requested_ref": "main",
        "resolved_revision": "abc123",
        "fingerprint": "sha256:first",
    }
    data.update(values)
    return Installation(**data)


def test_state_reads_are_lazy_when_database_does_not_exist(tmp_path):
    path = tmp_path / "state.sqlite"
    state = InstallState(path)

    assert state.get("wire") is None
    assert state.all() == []
    assert state.remove("wire") is False
    assert not path.exists()


def test_state_put_creates_database_and_round_trips_record(tmp_path):
    path = tmp_path / "state.sqlite"
    state = InstallState(path)

    stored = state.put(_record(tmp_path))
    loaded = state.get("wire")

    assert path.is_file()
    assert stored.installed_at is not None
    assert loaded == stored

    with sqlite3.connect(path) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
    assert version == 1


def test_state_put_reconciles_record_by_name_and_scope(tmp_path):
    state = InstallState(tmp_path / "state.sqlite")
    state.put(_record(tmp_path))

    updated = state.put(
        _record(
            tmp_path,
            resolved_revision="def456",
            fingerprint="sha256:second",
        )
    )

    assert state.get("wire") == updated
    assert state.get("wire").resolved_revision == "def456"
    assert len(state.all()) == 1


def test_state_keeps_user_and_system_records_distinct(tmp_path):
    state = InstallState(tmp_path / "state.sqlite")
    user = state.put(_record(tmp_path))
    system = state.put(
        _record(
            tmp_path,
            scope="system",
            install_path=tmp_path / "system" / "wire",
        )
    )

    assert state.get("wire", scope="user") == user
    assert state.get("wire", scope="system") == system
    assert state.all(scope="user") == [user]
    assert state.all(scope="system") == [system]


def test_state_remove_is_idempotent(tmp_path):
    state = InstallState(tmp_path / "state.sqlite")
    state.put(_record(tmp_path))

    assert state.remove("wire") is True
    assert state.remove("wire") is False
    assert state.get("wire") is None


def test_state_rejects_newer_schema_version(tmp_path):
    path = tmp_path / "state.sqlite"
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA user_version = 99")

    state = InstallState(path)

    with pytest.raises(RuntimeError, match="newer than this GWAY version"):
        state.all()
