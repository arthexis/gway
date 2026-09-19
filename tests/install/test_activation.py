import os
from pathlib import Path
import subprocess
import sys

import pytest

from gway.install import InstallRequest, InstallState, UninstallRequest, install_paths
import gway.install.transaction as transaction


def _project(tmp_path, name="tool"):
    root = tmp_path / "source" / name
    package = root / name
    package.mkdir(parents=True)
    (root / "gway.toml").write_text(
        f"[project]\nname = {name!r}\n\n"
        f"[install.scripts]\n{name} = {f'{name}:main'!r}\n",
        encoding="utf-8",
    )
    (package / "__init__.py").write_text(
        "def main():\n"
        "    print('managed launcher works')\n"
        "    return 0\n",
        encoding="utf-8",
    )
    return root


def _paths(tmp_path):
    return install_paths(
        root=tmp_path / "data",
        environ={"GWAY_BIN_DIR": str(tmp_path / "bin")},
        platform=sys.platform,
        home=tmp_path / "home",
    )


def test_install_activates_declared_script(tmp_path):
    source = _project(tmp_path)
    paths = _paths(tmp_path)

    installed = transaction.install_local(
        InstallRequest(str(source)),
        paths=paths,
    )

    launcher = paths.bin / "tool"
    assert launcher.is_file()
    assert os.access(launcher, os.X_OK)
    assert (paths.launchers / "tool.json").is_file()

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
    assert installed.install_path in Path(
        launcher.read_text(encoding="utf-8").splitlines()[4]
        .split("(", 1)[1]
        .rsplit(")", 1)[0]
        .strip("'\"")
    ).parents or str(installed.install_path) in launcher.read_text(encoding="utf-8")


def test_noop_install_repairs_missing_owned_launcher(tmp_path):
    source = _project(tmp_path)
    paths = _paths(tmp_path)
    installed = transaction.install_local(
        InstallRequest(str(source)),
        paths=paths,
    )
    launcher = paths.bin / "tool"
    launcher.unlink()

    repeated = transaction.install_local(
        InstallRequest(str(source)),
        paths=paths,
    )

    assert repeated == installed
    assert launcher.is_file()


def test_install_refuses_unmanaged_launcher_collision(tmp_path):
    source = _project(tmp_path)
    paths = _paths(tmp_path)
    paths.bin.mkdir(parents=True)
    launcher = paths.bin / "tool"
    launcher.write_text("#!/bin/sh\necho unrelated\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="unmanaged launcher"):
        transaction.install_local(
            InstallRequest(str(source)),
            paths=paths,
        )

    assert launcher.read_text(encoding="utf-8") == "#!/bin/sh\necho unrelated\n"
    assert not (paths.projects / "tool").exists()
    assert not paths.state.exists()


def test_state_failure_restores_previous_launcher_and_project(tmp_path):
    source = _project(tmp_path)
    paths = _paths(tmp_path)
    state = InstallState(paths.state)
    first = transaction.install_local(
        InstallRequest(str(source)),
        paths=paths,
        state=state,
    )
    launcher = paths.bin / "tool"
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
            paths=paths,
            state=FailingState(),
        )

    assert state.get("tool") == first
    assert launcher.read_text(encoding="utf-8") == original_launcher
    assert "managed launcher works" in (
        first.install_path / "tool" / "__init__.py"
    ).read_text(encoding="utf-8")


def test_uninstall_removes_owned_launcher_and_index(tmp_path):
    source = _project(tmp_path)
    paths = _paths(tmp_path)
    transaction.install_local(
        InstallRequest(str(source)),
        paths=paths,
    )

    removed = transaction.uninstall_local(
        UninstallRequest("tool"),
        paths=paths,
    )

    assert removed.name == "tool"
    assert not (paths.bin / "tool").exists()
    assert not (paths.launchers / "tool.json").exists()
    assert not (paths.projects / "tool").exists()


def test_uninstall_refuses_to_remove_replaced_unmanaged_launcher(tmp_path):
    source = _project(tmp_path)
    paths = _paths(tmp_path)
    transaction.install_local(
        InstallRequest(str(source)),
        paths=paths,
    )
    launcher = paths.bin / "tool"
    launcher.write_text("#!/bin/sh\necho replacement\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="unmanaged launcher"):
        transaction.uninstall_local(
            UninstallRequest("tool"),
            paths=paths,
        )

    assert launcher.read_text(encoding="utf-8") == "#!/bin/sh\necho replacement\n"
    assert (paths.projects / "tool").is_dir()
    assert InstallState(paths.state).get("tool") is not None
