from gway.identity import ExecutionIdentity


def test_execution_identity_round_trips_transaction_metadata():
    assert ExecutionIdentity.from_dict(ExecutionIdentity().as_dict()) == ExecutionIdentity()
    assert ExecutionIdentity.from_dict({"user": "root"}) == ExecutionIdentity("root")
    assert ExecutionIdentity.from_dict({"user": "www-data"}) == ExecutionIdentity(
        "www-data"
    )


def test_single_path_journal_uses_numbered_storage_and_identity(gateway, tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    destination = tmp_path / "destination.txt"

    gateway.copy(str(source), to=str(destination), rollback="deploy")

    entry = gateway.journal.require_open("deploy").entries[0]
    assert entry.data["identity"] == {"user": None}
    assert entry.data["paths"][0]["storage"] == "paths/000000"


def test_root_identity_is_persisted_for_rollback_capable_operation(
    gateway,
    tmp_path,
    host_calls,
):
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    destination = tmp_path / "destination.txt"

    gateway.copy(
        str(source),
        to=str(destination),
        sudo=True,
        rollback="deploy",
    )

    entry = gateway.journal.require_open("deploy").entries[0]
    assert entry.data["identity"] == {"user": "root"}
    assert host_calls[-1][0][:2] == ("sudo", "cp")


def test_named_identity_survives_manifest_reload(
    gateway,
    tmp_path,
    host_calls,
):
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    destination = tmp_path / "destination.txt"

    gateway.copy(
        str(source),
        to=str(destination),
        rollback="deploy",
        **{"as": "www-data"},
    )

    gateway.journal._journals.clear()
    entry = gateway.journal.require_open("deploy").entries[0]

    assert entry.data["identity"] == {"user": "www-data"}
    assert ExecutionIdentity.from_dict(entry.data["identity"]) == ExecutionIdentity(
        "www-data"
    )
    assert host_calls[-1][0][:4] == ("sudo", "-u", "www-data", "cp")
