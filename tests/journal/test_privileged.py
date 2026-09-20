import json
from types import SimpleNamespace


from gway.identity import ExecutionIdentity
import gway.snapshot as snapshot


def test_privileged_capture_streams_archive_into_private_storage(
    tmp_path,
    monkeypatch,
):
    target = tmp_path / "protected.txt"
    target.write_text("before", encoding="utf-8")
    storage = tmp_path / "journal" / "paths" / "000000"
    calls = []

    def fake_run(identity, *argv, **kwargs):
        calls.append((identity, tuple(str(value) for value in argv), kwargs))
        if argv[0] == "tar":
            kwargs["stdout"].write(b"archive-bytes")
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(snapshot, "run_as_identity", fake_run)

    captured = snapshot.capture_path(
        target,
        storage,
        identity=ExecutionIdentity("root"),
    )

    assert captured["path"] == str(target)
    assert captured["snapshot"] == "archive.tar"
    assert (storage / "archive.tar").read_bytes() == b"archive-bytes"
    assert (storage / "archive.tar").stat().st_mode & 0o777 == 0o600
    assert calls[0][0] == ExecutionIdentity("root")
    assert calls[0][1][:5] == (
        "tar",
        "-C",
        str(target.parent),
        "-cpf",
        "-",
    )


def test_privileged_capture_uses_identity_for_inaccessible_metadata(
    tmp_path,
    monkeypatch,
):
    target = tmp_path / "protected.txt"
    storage = tmp_path / "journal" / "paths" / "000000"
    identity = ExecutionIdentity("www-data")
    expected = {
        "path": str(target),
        "existed": False,
    }
    calls = []

    def inaccessible(path):
        raise PermissionError(path)

    def fake_run(seen_identity, *argv, **kwargs):
        calls.append((seen_identity, tuple(str(value) for value in argv), kwargs))
        return SimpleNamespace(returncode=0, stdout=json.dumps(expected))

    monkeypatch.setattr(snapshot, "_describe_local", inaccessible)
    monkeypatch.setattr(snapshot, "run_as_identity", fake_run)

    captured = snapshot.capture_path(target, storage, identity=identity)

    assert captured == expected
    assert calls[0][0] == identity
    assert calls[0][1][0] == str(snapshot.sys.executable)
    assert calls[0][1][-2:] == ("describe", str(target))


def test_privileged_fingerprint_falls_back_to_identity(
    tmp_path,
    monkeypatch,
):
    target = tmp_path / "protected.txt"
    identity = ExecutionIdentity("root")
    expected = {
        "path": str(target),
        "existed": True,
        "type": "file",
        "mode": 0o600,
        "uid": 0,
        "gid": 0,
        "mtime_ns": 123,
        "sha256": "abc",
    }

    def inaccessible(path):
        raise PermissionError(path)

    def fake_run(seen_identity, *argv, **kwargs):
        assert seen_identity == identity
        assert argv[-2:] == ("fingerprint", target)
        return SimpleNamespace(returncode=0, stdout=json.dumps(expected))

    monkeypatch.setattr(snapshot, "_fingerprint_local", inaccessible)
    monkeypatch.setattr(snapshot, "run_as_identity", fake_run)

    assert snapshot.fingerprint_path(target, identity=identity) == expected


def test_privileged_restore_verifies_then_restores_through_identity(
    tmp_path,
    monkeypatch,
):
    target = tmp_path / "protected.txt"
    target.write_text("after", encoding="utf-8")
    storage = tmp_path / "journal" / "paths" / "000000"
    storage.mkdir(parents=True)
    (storage / "archive.tar").write_bytes(b"archive")
    identity = ExecutionIdentity("root")
    expected = {"path": str(target), "existed": False}
    captured = {
        "path": str(target),
        "existed": True,
        "type": "file",
        "snapshot": "archive.tar",
    }
    events = []

    def fake_verify(value, *, identity=None):
        events.append(("verify", value, identity))

    def fake_run(seen_identity, *argv, **kwargs):
        events.append(("run", seen_identity, tuple(str(value) for value in argv)))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(snapshot, "verify_fingerprint", fake_verify)
    monkeypatch.setattr(snapshot, "run_as_identity", fake_run)

    result = snapshot.restore_path(
        captured,
        storage,
        expected=expected,
        identity=identity,
    )

    assert result == target
    assert events[0] == ("verify", expected, identity)
    assert events[1][2][:4] == ("rm", "-rf", "--", str(target))
    assert events[2][2][:5] == (
        "tar",
        "-C",
        str(target.parent),
        "-xpf",
        "-",
    )


def test_privileged_restore_of_original_absence_only_removes_current_path(
    tmp_path,
    monkeypatch,
):
    target = tmp_path / "created.txt"
    identity = ExecutionIdentity("www-data")
    captured = {"path": str(target), "existed": False}
    calls = []

    monkeypatch.setattr(
        snapshot,
        "verify_fingerprint",
        lambda *args, **kwargs: None,
    )

    def fake_run(seen_identity, *argv, **kwargs):
        calls.append((seen_identity, tuple(str(value) for value in argv)))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(snapshot, "run_as_identity", fake_run)

    snapshot.restore_path(
        captured,
        tmp_path / "storage",
        expected={"path": str(target), "existed": True},
        identity=identity,
    )

    assert calls == [
        (
            identity,
            ("rm", "-rf", "--", str(target)),
        )
    ]


def test_unprivileged_snapshot_path_never_invokes_host_boundary(
    tmp_path,
    monkeypatch,
):
    target = tmp_path / "local.txt"
    target.write_text("local", encoding="utf-8")

    def forbidden(*args, **kwargs):
        raise AssertionError("host boundary should not be used")

    monkeypatch.setattr(snapshot, "run_as_identity", forbidden)

    captured = snapshot.capture_path(
        target,
        tmp_path / "storage",
        identity=ExecutionIdentity(),
    )

    assert captured["type"] == "file"
    assert snapshot.fingerprint_path(target, identity=ExecutionIdentity())["type"] == "file"
