import os
import subprocess

import pytest

from gway.install import InstallRequest, InstallState, UninstallRequest
import gway.install.transaction as transaction


def test_install_activates_declared_script(make_project, managed_paths, tmp_path):
    source = make_project("tool", launcher=True)

    installed = transaction.install_local(
        InstallRequest(str(source)),
        paths=managed_paths,
    )

    launcher = managed_paths.bin / "tool"
    assert launcher.is_file()
    assert os.access(launcher, os.X_OK)
    assert (managed_paths.launchers / "tool.json").is_file()

    result = subprocess.run(
        [str(launcher)],
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "managed launcher works"
    assert str(installed.install_path) in launcher.read_text(encoding="utf-8")


def test_noop_install_repairs_missing_owned_launcher(make_project, managed_paths):
    source = make_project("tool", launcher=True)
    installed = transaction.install_local(
        InstallRequest(str(source)),
        paths=managed_paths,
    )
    launcher = managed_paths.bin / "tool"
    launcher.unlink()

    repeated = transaction.install_local(
        InstallRequest(str(source)),
        paths=managed_paths,
    )

    assert repeated == installed
    assert launcher.is_file()


def test_install_refuses_unmanaged_launcher_collision(make_project, managed_paths):
    source = make_project("tool", launcher=True)
    managed_paths.bin.mkdir(parents=True)
    launcher = managed_paths.bin / "tool"
    launcher.write_text("#!/bin/sh\necho unrelated\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="unmanaged launcher"):
        transaction.install_local(
            InstallRequest(str(source)),
            paths=managed_paths,
        )

    assert launcher.read_text(encoding="utf-8") == "#!/bin/sh\necho unrelated\n"
    assert not (managed_paths.projects / "tool").exists()
    assert not managed_paths.state.exists()


def test_state_failure_restores_previous_launcher_and_project(
    make_project,
    managed_paths,
):
    source = make_project("tool", launcher=True)
    state = InstallState(managed_paths.state)
    first = transaction.install_local(
        InstallRequest(str(source)),
        paths=managed_paths,
        state=state,
    )
    launcher = managed_paths.bin / "tool"
    original_launcher = launcher.read_text(encoding="utf-8")

    (source / "tool" / "__init__.py").write_text(
        "def main():\n"
        "    print('new version')\n"
        "    return 0\n",
        encoding="utf-8",
    )

    class FailingState:
        def get(self, name, *, scope="user"):
            return state.get(name, scope=scope)

        def put(self, installation):
            raise RuntimeError("state failed")

    with pytest.raises(RuntimeError, match="state failed"):
        transaction.install_local(
            InstallRequest(str(source)),
            paths=managed_paths,
            state=FailingState(),
        )

    assert state.get("tool") == first
    assert launcher.read_text(encoding="utf-8") == original_launcher
    assert "managed launcher works" in (
        first.install_path / "tool" / "__init__.py"
    ).read_text(encoding="utf-8")


def test_uninstall_removes_owned_launcher_and_index(make_project, managed_paths):
    source = make_project("tool", launcher=True)
    transaction.install_local(
        InstallRequest(str(source)),
        paths=managed_paths,
    )

    removed = transaction.uninstall_local(
        UninstallRequest("tool"),
        paths=managed_paths,
    )

    assert removed.name == "tool"
    assert not (managed_paths.bin / "tool").exists()
    assert not (managed_paths.launchers / "tool.json").exists()
    assert not (managed_paths.projects / "tool").exists()


def test_uninstall_refuses_to_remove_replaced_unmanaged_launcher(
    make_project,
    managed_paths,
):
    source = make_project("tool", launcher=True)
    transaction.install_local(
        InstallRequest(str(source)),
        paths=managed_paths,
    )
    launcher = managed_paths.bin / "tool"
    launcher.write_text("#!/bin/sh\necho replacement\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="unmanaged launcher"):
        transaction.uninstall_local(
            UninstallRequest("tool"),
            paths=managed_paths,
        )

    assert launcher.read_text(encoding="utf-8") == "#!/bin/sh\necho replacement\n"
    assert (managed_paths.projects / "tool").is_dir()
    assert InstallState(managed_paths.state).get("tool") is not None
