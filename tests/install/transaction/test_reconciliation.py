import pytest

from gway.install import InstallRequest, InstallState
import gway.install.transaction as transaction


def test_changed_local_source_is_reconciled_when_upgrade_enabled(
    make_project,
    managed_paths,
):
    source = make_project("wire")
    first = transaction.install_local(
        InstallRequest(str(source)),
        paths=managed_paths,
    )
    (source / "module.py").write_text("VALUE = 2\n", encoding="utf-8")

    second = transaction.install_local(
        InstallRequest(str(source)),
        paths=managed_paths,
    )

    assert second.name == first.name
    assert second.install_path == first.install_path
    assert second.fingerprint != first.fingerprint
    assert (managed_paths.projects / "wire" / "module.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 2\n"
    assert InstallState(managed_paths.state).get("wire") == second
    assert list(managed_paths.projects.glob(".wire.replace-*")) == []


def test_no_upgrade_leaves_existing_installation_unchanged(
    make_project,
    managed_paths,
):
    source = make_project("wire")
    first = transaction.install_local(
        InstallRequest(str(source)),
        paths=managed_paths,
    )
    (source / "module.py").write_text("VALUE = 2\n", encoding="utf-8")

    second = transaction.install_local(
        InstallRequest(str(source), upgrade=False),
        paths=managed_paths,
    )

    assert second == first
    assert (first.install_path / "module.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 1\n"


def test_missing_managed_copy_is_repaired_even_with_no_upgrade(
    make_project,
    managed_paths,
):
    source = make_project("wire")
    first = transaction.install_local(
        InstallRequest(str(source)),
        paths=managed_paths,
    )
    transaction._remove_path(first.install_path)

    repaired = transaction.install_local(
        InstallRequest(str(source), upgrade=False),
        paths=managed_paths,
    )

    assert repaired.install_path.is_dir()
    assert (repaired.install_path / "module.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 1\n"
    assert InstallState(managed_paths.state).get("wire") == repaired


def test_identical_content_from_new_source_updates_provenance_without_swap(
    make_project,
    managed_paths,
    tmp_path,
):
    first_source = make_project("wire")
    first = transaction.install_local(
        InstallRequest(str(first_source)),
        paths=managed_paths,
    )

    second_source = tmp_path / "alternate" / "wire"
    second_source.mkdir(parents=True)
    (second_source / "pyproject.toml").write_text(
        "[project]\nname = 'wire'\n",
        encoding="utf-8",
    )
    (second_source / "module.py").write_text(
        "VALUE = 1\n",
        encoding="utf-8",
    )

    second = transaction.install_local(
        InstallRequest(str(second_source)),
        paths=managed_paths,
    )

    assert second.fingerprint == first.fingerprint
    assert second.source == str(second_source.resolve())
    assert second.install_path == first.install_path
    assert second.installed_at == first.installed_at
    assert list(managed_paths.projects.glob(".wire.replace-*")) == []


def test_missing_managed_copy_with_changed_source_respects_no_upgrade(
    make_project,
    managed_paths,
):
    source = make_project("wire")
    first = transaction.install_local(
        InstallRequest(str(source)),
        paths=managed_paths,
    )
    transaction._remove_path(first.install_path)
    (source / "module.py").write_text("VALUE = 2\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="would require an upgrade"):
        transaction.install_local(
            InstallRequest(str(source), upgrade=False),
            paths=managed_paths,
        )

    assert not first.install_path.exists()
    assert InstallState(managed_paths.state).get("wire") == first
