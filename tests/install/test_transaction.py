import pytest

from gway.install import InstallRequest, InstallState, UninstallRequest, install_paths
import gway.install.transaction as transaction


def _project(tmp_path, name="demo"):
    root = tmp_path / "source" / name
    root.mkdir(parents=True)
    (root / "gway.toml").write_text(
        f"[project]\nname = {name!r}\n",
        encoding="utf-8",
    )
    (root / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    return root


def test_local_install_stages_copy_and_records_managed_project(tmp_path):
    source = _project(tmp_path, "wire")
    paths = install_paths(root=tmp_path / "data")

    installed = transaction.install_local(
        InstallRequest(str(source)),
        paths=paths,
    )

    destination = paths.projects / "wire"
    assert installed.name == "wire"
    assert installed.source == str(source.resolve())
    assert installed.install_path == destination
    assert installed.fingerprint.startswith("sha256:")
    assert installed.installed_at is not None
    assert (destination / "gway.toml").is_file()
    assert (destination / "module.py").read_text(encoding="utf-8") == "VALUE = 1\n"
    assert InstallState(paths.state).get("wire") == installed


def test_local_install_does_not_modify_source_tree(tmp_path):
    source = _project(tmp_path)
    before = sorted(
        path.relative_to(source).as_posix()
        for path in source.rglob("*")
    )
    paths = install_paths(root=tmp_path / "data")

    transaction.install_local(InstallRequest(str(source)), paths=paths)

    after = sorted(
        path.relative_to(source).as_posix()
        for path in source.rglob("*")
    )
    assert after == before
    assert source != paths.projects / "demo"


def test_repeated_unchanged_local_install_is_noop(tmp_path):
    source = _project(tmp_path, "wire")
    paths = install_paths(root=tmp_path / "data")
    request = InstallRequest(str(source))

    first = transaction.install_local(request, paths=paths)
    second = transaction.install_local(request, paths=paths)

    assert second == first
    assert len(InstallState(paths.state).all()) == 1


def test_changed_local_source_is_reconciled_when_upgrade_enabled(tmp_path):
    source = _project(tmp_path, "wire")
    paths = install_paths(root=tmp_path / "data")
    first = transaction.install_local(InstallRequest(str(source)), paths=paths)
    (source / "module.py").write_text("VALUE = 2\n", encoding="utf-8")

    second = transaction.install_local(InstallRequest(str(source)), paths=paths)

    assert second.name == first.name
    assert second.install_path == first.install_path
    assert second.fingerprint != first.fingerprint
    assert (paths.projects / "wire" / "module.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 2\n"
    assert InstallState(paths.state).get("wire") == second
    assert list(paths.projects.glob(".wire.replace-*")) == []


def test_no_upgrade_leaves_existing_installation_unchanged(tmp_path):
    source = _project(tmp_path, "wire")
    paths = install_paths(root=tmp_path / "data")
    first = transaction.install_local(InstallRequest(str(source)), paths=paths)
    (source / "module.py").write_text("VALUE = 2\n", encoding="utf-8")

    second = transaction.install_local(
        InstallRequest(str(source), upgrade=False),
        paths=paths,
    )

    assert second == first
    assert (paths.projects / "wire" / "module.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 1\n"


def test_local_install_ref_is_rejected_until_git_source_support(tmp_path):
    source = _project(tmp_path)

    with pytest.raises(ValueError, match="not supported for local"):
        transaction.install_local(
            InstallRequest(str(source), ref="main"),
            paths=install_paths(root=tmp_path / "data"),
        )


def test_installation_root_cannot_live_inside_source_tree(tmp_path):
    source = _project(tmp_path)

    with pytest.raises(ValueError, match="cannot be stored inside"):
        transaction.install_local(
            InstallRequest(str(source)),
            paths=install_paths(root=source / ".gway-data"),
        )


def test_unmanaged_destination_is_never_overwritten(tmp_path):
    source = _project(tmp_path, "wire")
    paths = install_paths(root=tmp_path / "data")
    destination = paths.projects / "wire"
    destination.mkdir(parents=True)
    (destination / "keep.txt").write_text("mine", encoding="utf-8")

    with pytest.raises(RuntimeError, match="without installation state"):
        transaction.install_local(InstallRequest(str(source)), paths=paths)

    assert (destination / "keep.txt").read_text(encoding="utf-8") == "mine"


def test_install_failure_removes_staging_directory(tmp_path, monkeypatch):
    source = _project(tmp_path, "wire")
    paths = install_paths(root=tmp_path / "data")

    def fail_copy(source, stage):
        (stage / "partial.txt").write_text("partial", encoding="utf-8")
        raise RuntimeError("copy failed")

    monkeypatch.setattr(transaction, "_copy_project", fail_copy)

    with pytest.raises(RuntimeError, match="copy failed"):
        transaction.install_local(InstallRequest(str(source)), paths=paths)

    assert not (paths.projects / "wire").exists()
    assert list(paths.projects.glob(".wire.stage-*")) == []
    assert not paths.state.exists()


def test_uninstall_removes_managed_copy_and_state_but_not_source(tmp_path):
    source = _project(tmp_path, "wire")
    paths = install_paths(root=tmp_path / "data")
    installed = transaction.install_local(InstallRequest(str(source)), paths=paths)

    removed = transaction.uninstall_local(
        UninstallRequest("wire"),
        paths=paths,
    )

    assert removed == installed
    assert source.is_dir()
    assert not installed.install_path.exists()
    assert InstallState(paths.state).get("wire") is None


def test_uninstall_is_idempotent_when_project_is_absent(tmp_path):
    paths = install_paths(root=tmp_path / "data")

    assert transaction.uninstall_local(
        UninstallRequest("missing"),
        paths=paths,
    ) is None
    assert not paths.root.exists()


def test_uninstall_reconciles_stale_record_when_managed_copy_is_missing(tmp_path):
    source = _project(tmp_path, "wire")
    paths = install_paths(root=tmp_path / "data")
    installed = transaction.install_local(InstallRequest(str(source)), paths=paths)
    transaction._remove_path(installed.install_path)

    removed = transaction.uninstall_local(
        UninstallRequest("wire"),
        paths=paths,
    )

    assert removed == installed
    assert InstallState(paths.state).get("wire") is None



def test_install_rolls_back_activation_when_state_write_fails(tmp_path):
    source = _project(tmp_path, "wire")
    paths = install_paths(root=tmp_path / "data")

    class FailingState:
        def get(self, name, *, scope="user"):
            return None

        def put(self, installation):
            raise RuntimeError("state write failed")

    with pytest.raises(RuntimeError, match="state write failed"):
        transaction.install_local(
            InstallRequest(str(source)),
            paths=paths,
            state=FailingState(),
        )

    assert not (paths.projects / "wire").exists()
    assert list(paths.projects.glob(".wire.stage-*")) == []


def test_uninstall_restores_live_directory_when_state_remove_fails(
    tmp_path,
    monkeypatch,
):
    source = _project(tmp_path, "wire")
    paths = install_paths(root=tmp_path / "data")
    state = InstallState(paths.state)
    installed = transaction.install_local(
        InstallRequest(str(source)),
        paths=paths,
        state=state,
    )

    def fail_remove(name, *, scope="user"):
        raise RuntimeError("state remove failed")

    monkeypatch.setattr(state, "remove", fail_remove)

    with pytest.raises(RuntimeError, match="state remove failed"):
        transaction.uninstall_local(
            UninstallRequest("wire"),
            paths=paths,
            state=state,
        )

    assert installed.install_path.is_dir()
    assert (installed.install_path / "module.py").is_file()
    assert state.get("wire") == installed


def test_uninstall_refuses_registry_path_outside_managed_projects(tmp_path):
    paths = install_paths(root=tmp_path / "data")
    outside = tmp_path / "outside"
    outside.mkdir()
    marker = outside / "keep.txt"
    marker.write_text("safe", encoding="utf-8")
    state = InstallState(paths.state)
    state.put(
        transaction.Installation(
            name="wire",
            source=str(tmp_path / "source"),
            install_path=outside,
        )
    )

    with pytest.raises(RuntimeError, match="outside the managed"):
        transaction.uninstall_local(
            UninstallRequest("wire"),
            paths=paths,
            state=state,
        )

    assert marker.read_text(encoding="utf-8") == "safe"



def test_changed_local_source_replacement_is_atomic_on_state_failure(tmp_path):
    source = _project(tmp_path, "wire")
    paths = install_paths(root=tmp_path / "data")
    state = InstallState(paths.state)
    first = transaction.install_local(
        InstallRequest(str(source)),
        paths=paths,
        state=state,
    )
    original_fingerprint = first.fingerprint
    (source / "module.py").write_text("VALUE = 2\n", encoding="utf-8")

    class FailingReplacementState:
        def get(self, name, *, scope="user"):
            return state.get(name, scope=scope)

        def put(self, installation):
            raise RuntimeError("replacement state write failed")

    with pytest.raises(RuntimeError, match="replacement state write failed"):
        transaction.install_local(
            InstallRequest(str(source)),
            paths=paths,
            state=FailingReplacementState(),
        )

    assert (paths.projects / "wire" / "module.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 1\n"
    assert state.get("wire").fingerprint == original_fingerprint
    assert list(paths.projects.glob(".wire.replace-*")) == []
    assert list(paths.projects.glob(".wire.stage-*")) == []


def test_missing_managed_copy_is_repaired_even_with_no_upgrade(tmp_path):
    source = _project(tmp_path, "wire")
    paths = install_paths(root=tmp_path / "data")
    first = transaction.install_local(InstallRequest(str(source)), paths=paths)
    transaction._remove_path(first.install_path)

    repaired = transaction.install_local(
        InstallRequest(str(source), upgrade=False),
        paths=paths,
    )

    assert repaired.install_path.is_dir()
    assert (repaired.install_path / "module.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 1\n"
    assert InstallState(paths.state).get("wire") == repaired


def test_identical_content_from_new_source_updates_provenance_without_swap(tmp_path):
    first_source = _project(tmp_path, "wire")
    paths = install_paths(root=tmp_path / "data")
    first = transaction.install_local(
        InstallRequest(str(first_source)),
        paths=paths,
    )

    second_source = tmp_path / "alternate" / "wire"
    second_source.mkdir(parents=True)
    (second_source / "gway.toml").write_text(
        "[project]\nname = 'wire'\n",
        encoding="utf-8",
    )
    (second_source / "module.py").write_text("VALUE = 1\n", encoding="utf-8")

    second = transaction.install_local(
        InstallRequest(str(second_source)),
        paths=paths,
    )

    assert second.fingerprint == first.fingerprint
    assert second.source == str(second_source.resolve())
    assert second.install_path == first.install_path
    assert second.installed_at == first.installed_at
    assert list(paths.projects.glob(".wire.replace-*")) == []


def test_managed_tree_drift_blocks_even_an_unchanged_reinstall(tmp_path):
    source = _project(tmp_path, "wire")
    paths = install_paths(root=tmp_path / "data")
    installed = transaction.install_local(
        InstallRequest(str(source)),
        paths=paths,
    )
    managed_file = installed.install_path / "module.py"
    managed_file.write_text("CUSTOM = True\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="local modifications"):
        transaction.install_local(
            InstallRequest(str(source)),
            paths=paths,
        )

    assert managed_file.read_text(encoding="utf-8") == "CUSTOM = True\n"
    assert InstallState(paths.state).get("wire") == installed


def test_managed_tree_drift_blocks_source_upgrade_before_swap(tmp_path):
    source = _project(tmp_path, "wire")
    paths = install_paths(root=tmp_path / "data")
    installed = transaction.install_local(
        InstallRequest(str(source)),
        paths=paths,
    )
    (installed.install_path / "module.py").write_text(
        "CUSTOM = True\n",
        encoding="utf-8",
    )
    (source / "module.py").write_text("VALUE = 2\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="local modifications"):
        transaction.install_local(
            InstallRequest(str(source)),
            paths=paths,
        )

    assert (installed.install_path / "module.py").read_text(
        encoding="utf-8"
    ) == "CUSTOM = True\n"
    assert list(paths.projects.glob(".wire.replace-*")) == []
    assert list(paths.projects.glob(".wire.stage-*")) == []



def test_missing_managed_copy_with_changed_source_respects_no_upgrade(tmp_path):
    source = _project(tmp_path, "wire")
    paths = install_paths(root=tmp_path / "data")
    first = transaction.install_local(InstallRequest(str(source)), paths=paths)
    transaction._remove_path(first.install_path)
    (source / "module.py").write_text("VALUE = 2\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="would require an upgrade"):
        transaction.install_local(
            InstallRequest(str(source), upgrade=False),
            paths=paths,
        )

    assert not first.install_path.exists()
    assert InstallState(paths.state).get("wire") == first



def test_force_discards_managed_drift_and_reinstalls_clean_source(
    tmp_path,
    caplog,
):
    source = _project(tmp_path, "wire")
    paths = install_paths(root=tmp_path / "data")
    installed = transaction.install_local(
        InstallRequest(str(source)),
        paths=paths,
    )
    managed = installed.install_path / "module.py"
    managed.write_text("CUSTOM = True\n", encoding="utf-8")

    repaired = transaction.install_local(
        InstallRequest(str(source), force=True),
        paths=paths,
    )

    assert managed.read_text(encoding="utf-8") == "VALUE = 1\n"
    assert repaired.fingerprint == transaction.fingerprint(source)
    assert "Discarding local modifications for wire" in caplog.text
    assert not paths.stashes.exists()


def test_force_can_repair_drift_without_enabling_source_upgrade(
    tmp_path,
):
    source = _project(tmp_path, "wire")
    paths = install_paths(root=tmp_path / "data")
    installed = transaction.install_local(
        InstallRequest(str(source)),
        paths=paths,
    )
    managed = installed.install_path / "module.py"
    managed.write_text("CUSTOM = True\n", encoding="utf-8")

    repaired = transaction.install_local(
        InstallRequest(str(source), force=True, upgrade=False),
        paths=paths,
    )

    assert managed.read_text(encoding="utf-8") == "VALUE = 1\n"
    assert repaired.fingerprint == installed.fingerprint


def test_stash_preserves_managed_drift_before_reinstall(tmp_path, caplog):
    source = _project(tmp_path, "wire")
    paths = install_paths(root=tmp_path / "data")
    installed = transaction.install_local(
        InstallRequest(str(source)),
        paths=paths,
    )
    managed = installed.install_path / "module.py"
    managed.write_text("CUSTOM = True\n", encoding="utf-8")

    repaired = transaction.install_local(
        InstallRequest(str(source), stash=True),
        paths=paths,
    )

    stashes = list((paths.stashes / "wire").iterdir())
    assert len(stashes) == 1
    assert (stashes[0] / "tree" / "module.py").read_text(
        encoding="utf-8"
    ) == "CUSTOM = True\n"
    assert managed.read_text(encoding="utf-8") == "VALUE = 1\n"
    assert repaired.fingerprint == installed.fingerprint
    assert "Preserved local modifications for wire at" in caplog.text


def test_stash_preserves_drift_then_applies_source_upgrade(tmp_path):
    source = _project(tmp_path, "wire")
    paths = install_paths(root=tmp_path / "data")
    installed = transaction.install_local(
        InstallRequest(str(source)),
        paths=paths,
    )
    managed = installed.install_path / "module.py"
    managed.write_text("CUSTOM = True\n", encoding="utf-8")
    (source / "module.py").write_text("VALUE = 2\n", encoding="utf-8")

    upgraded = transaction.install_local(
        InstallRequest(str(source), stash=True),
        paths=paths,
    )

    stashes = list((paths.stashes / "wire").iterdir())
    assert len(stashes) == 1
    assert (stashes[0] / "tree" / "module.py").read_text(
        encoding="utf-8"
    ) == "CUSTOM = True\n"
    assert managed.read_text(encoding="utf-8") == "VALUE = 2\n"
    assert upgraded.fingerprint != installed.fingerprint


@pytest.mark.parametrize("mutation", [{"force": True}, {"stash": True}])
def test_no_upgrade_with_changed_source_never_uses_mutation_override(
    tmp_path,
    mutation,
):
    source = _project(tmp_path, "wire")
    paths = install_paths(root=tmp_path / "data")
    installed = transaction.install_local(
        InstallRequest(str(source)),
        paths=paths,
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
            paths=paths,
        )

    assert managed.read_text(encoding="utf-8") == "CUSTOM = True\n"
    assert not paths.stashes.exists()


def test_stash_failure_leaves_managed_tree_untouched(
    tmp_path,
    monkeypatch,
):
    source = _project(tmp_path, "wire")
    paths = install_paths(root=tmp_path / "data")
    installed = transaction.install_local(
        InstallRequest(str(source)),
        paths=paths,
    )
    managed = installed.install_path / "module.py"
    managed.write_text("CUSTOM = True\n", encoding="utf-8")

    def fail_stash(*args, **kwargs):
        raise RuntimeError("stash failed")

    monkeypatch.setattr(transaction, "preserve_stash", fail_stash)

    with pytest.raises(RuntimeError, match="stash failed"):
        transaction.install_local(
            InstallRequest(str(source), stash=True),
            paths=paths,
        )

    assert managed.read_text(encoding="utf-8") == "CUSTOM = True\n"
    assert list(paths.projects.glob(".wire.stage-*")) == []
    assert list(paths.projects.glob(".wire.replace-*")) == []
