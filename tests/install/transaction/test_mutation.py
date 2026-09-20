import pytest

from gway.install import InstallRequest, InstallState
import gway.install.transaction as transaction


def test_managed_tree_drift_blocks_unchanged_reinstall(
    make_project,
    managed_paths,
):
    source = make_project("wire")
    installed = transaction.install_local(
        InstallRequest(str(source)),
        paths=managed_paths,
    )
    managed = installed.install_path / "module.py"
    managed.write_text("CUSTOM = True\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="local modifications"):
        transaction.install_local(
            InstallRequest(str(source)),
            paths=managed_paths,
        )

    assert managed.read_text(encoding="utf-8") == "CUSTOM = True\n"
    assert InstallState(managed_paths.state).get("wire") == installed


def test_managed_tree_drift_blocks_source_upgrade_before_swap(
    make_project,
    managed_paths,
):
    source = make_project("wire")
    installed = transaction.install_local(
        InstallRequest(str(source)),
        paths=managed_paths,
    )
    managed = installed.install_path / "module.py"
    managed.write_text("CUSTOM = True\n", encoding="utf-8")
    (source / "module.py").write_text("VALUE = 2\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="local modifications"):
        transaction.install_local(
            InstallRequest(str(source)),
            paths=managed_paths,
        )

    assert managed.read_text(encoding="utf-8") == "CUSTOM = True\n"
    assert list(managed_paths.projects.glob(".wire.replace-*")) == []
    assert list(managed_paths.projects.glob(".wire.stage-*")) == []


def test_force_discards_managed_drift_and_reinstalls_clean_source(
    make_project,
    managed_paths,
    caplog,
):
    source = make_project("wire")
    installed = transaction.install_local(
        InstallRequest(str(source)),
        paths=managed_paths,
    )
    managed = installed.install_path / "module.py"
    managed.write_text("CUSTOM = True\n", encoding="utf-8")

    repaired = transaction.install_local(
        InstallRequest(str(source), force=True),
        paths=managed_paths,
    )

    assert managed.read_text(encoding="utf-8") == "VALUE = 1\n"
    assert repaired.fingerprint == transaction.fingerprint(source)
    assert "Discarding local modifications for wire" in caplog.text
    assert not managed_paths.stashes.exists()


def test_force_can_repair_drift_without_enabling_source_upgrade(
    make_project,
    managed_paths,
):
    source = make_project("wire")
    installed = transaction.install_local(
        InstallRequest(str(source)),
        paths=managed_paths,
    )
    managed = installed.install_path / "module.py"
    managed.write_text("CUSTOM = True\n", encoding="utf-8")

    repaired = transaction.install_local(
        InstallRequest(str(source), force=True, upgrade=False),
        paths=managed_paths,
    )

    assert managed.read_text(encoding="utf-8") == "VALUE = 1\n"
    assert repaired.fingerprint == installed.fingerprint


def test_stash_preserves_managed_drift_before_reinstall(
    make_project,
    managed_paths,
    caplog,
):
    source = make_project("wire")
    installed = transaction.install_local(
        InstallRequest(str(source)),
        paths=managed_paths,
    )
    managed = installed.install_path / "module.py"
    managed.write_text("CUSTOM = True\n", encoding="utf-8")

    repaired = transaction.install_local(
        InstallRequest(str(source), stash=True),
        paths=managed_paths,
    )

    stashes = list((managed_paths.stashes / "wire").iterdir())
    assert len(stashes) == 1
    assert (stashes[0] / "tree" / "module.py").read_text(
        encoding="utf-8"
    ) == "CUSTOM = True\n"
    assert managed.read_text(encoding="utf-8") == "VALUE = 1\n"
    assert repaired.fingerprint == installed.fingerprint
    assert "Preserved local modifications for wire at" in caplog.text


def test_stash_preserves_drift_then_applies_source_upgrade(
    make_project,
    managed_paths,
):
    source = make_project("wire")
    installed = transaction.install_local(
        InstallRequest(str(source)),
        paths=managed_paths,
    )
    managed = installed.install_path / "module.py"
    managed.write_text("CUSTOM = True\n", encoding="utf-8")
    (source / "module.py").write_text("VALUE = 2\n", encoding="utf-8")

    upgraded = transaction.install_local(
        InstallRequest(str(source), stash=True),
        paths=managed_paths,
    )

    stashes = list((managed_paths.stashes / "wire").iterdir())
    assert len(stashes) == 1
    assert (stashes[0] / "tree" / "module.py").read_text(
        encoding="utf-8"
    ) == "CUSTOM = True\n"
    assert managed.read_text(encoding="utf-8") == "VALUE = 2\n"
    assert upgraded.fingerprint != installed.fingerprint


@pytest.mark.parametrize("mutation", [{"force": True}, {"stash": True}])
def test_no_upgrade_with_changed_source_never_uses_mutation_override(
    make_project,
    managed_paths,
    mutation,
):
    source = make_project("wire")
    installed = transaction.install_local(
        InstallRequest(str(source)),
        paths=managed_paths,
    )
    managed = installed.install_path / "module.py"
    managed.write_text("CUSTOM = True\n", encoding="utf-8")
    (source / "module.py").write_text("VALUE = 2\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="--no-upgrade prevents"):
        transaction.install_local(
            InstallRequest(
                str(source),
                upgrade=False,
                **mutation,
            ),
            paths=managed_paths,
        )

    assert managed.read_text(encoding="utf-8") == "CUSTOM = True\n"
    assert not managed_paths.stashes.exists()


def test_stash_failure_leaves_managed_tree_untouched(
    make_project,
    managed_paths,
    monkeypatch,
):
    source = make_project("wire")
    installed = transaction.install_local(
        InstallRequest(str(source)),
        paths=managed_paths,
    )
    managed = installed.install_path / "module.py"
    managed.write_text("CUSTOM = True\n", encoding="utf-8")

    def fail_stash(*args, **kwargs):
        raise RuntimeError("stash failed")

    monkeypatch.setattr(transaction, "preserve_stash", fail_stash)

    with pytest.raises(RuntimeError, match="stash failed"):
        transaction.install_local(
            InstallRequest(str(source), stash=True),
            paths=managed_paths,
        )

    assert managed.read_text(encoding="utf-8") == "CUSTOM = True\n"
    assert list(managed_paths.projects.glob(".wire.stage-*")) == []
    assert list(managed_paths.projects.glob(".wire.replace-*")) == []
