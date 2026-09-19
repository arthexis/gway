from gway.install import data_root, install_paths


def test_user_data_root_uses_xdg_data_home(tmp_path):
    base = tmp_path / "xdg"

    assert data_root(
        environ={"XDG_DATA_HOME": str(base)},
        platform="linux",
        home=tmp_path / "home",
    ) == base / "gway"


def test_user_data_root_falls_back_to_local_share(tmp_path):
    home = tmp_path / "home"

    assert data_root(
        environ={},
        platform="linux",
        home=home,
    ) == home / ".local" / "share" / "gway"


def test_system_data_root_is_separate_from_user_data(tmp_path):
    assert data_root(
        system=True,
        environ={},
        platform="linux",
        home=tmp_path / "home",
    ).as_posix() == "/var/lib/gway"


def test_data_root_overrides_are_scope_specific(tmp_path):
    user = tmp_path / "user"
    system = tmp_path / "system"
    environ = {
        "GWAY_DATA_DIR": str(user),
        "GWAY_SYSTEM_DATA_DIR": str(system),
    }

    assert data_root(environ=environ, platform="linux") == user
    assert data_root(system=True, environ=environ, platform="linux") == system


def test_install_paths_are_durable_and_lazy(tmp_path):
    root = tmp_path / "gway-data"

    paths = install_paths(root=root)

    assert paths.root == root.resolve()
    assert paths.projects == root.resolve() / "projects"
    assert paths.stashes == root.resolve() / "stashes"
    assert paths.state == root.resolve() / "state.sqlite"
    assert paths.scope == "user"
    assert not root.exists()


def test_system_install_paths_report_system_scope(tmp_path):
    paths = install_paths(system=True, root=tmp_path / "system-data")

    assert paths.scope == "system"
