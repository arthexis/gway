from gway.install import bin_root, data_root, install_paths


def test_user_data_root_uses_xdg_data_home(tmp_path):
    base = tmp_path / "xdg"

    assert (
        data_root(
            environ={"XDG_DATA_HOME": str(base)},
            platform="linux",
            home=tmp_path / "home",
        )
        == base / "gway"
    )


def test_user_data_root_falls_back_to_local_share(tmp_path):
    home = tmp_path / "home"

    assert (
        data_root(
            environ={},
            platform="linux",
            home=home,
        )
        == home / ".local" / "share" / "gway"
    )


def test_system_data_root_is_separate_from_user_data(tmp_path):
    assert (
        data_root(
            system=True,
            environ={},
            platform="linux",
            home=tmp_path / "home",
        ).as_posix()
        == "/var/lib/gway"
    )


def test_data_root_accepts_explicit_semantic_override(tmp_path):
    user = tmp_path / "user"
    system = tmp_path / "system"

    assert data_root(data_dir=user, platform="linux") == user
    assert data_root(system=True, data_dir=system, platform="linux") == system


def test_install_paths_are_durable_and_lazy(tmp_path):
    root = tmp_path / "gway-data"

    paths = install_paths(root=root)

    assert paths.root == root.resolve()
    assert paths.projects == root.resolve() / "projects"
    assert paths.stashes == root.resolve() / "stashes"
    assert paths.launchers == root.resolve() / "launchers"
    assert paths.state == root.resolve() / "state.sqlite"
    assert paths.scope == "user"
    assert not root.exists()


def test_system_install_paths_report_system_scope(tmp_path):
    paths = install_paths(system=True, root=tmp_path / "system-data")

    assert paths.scope == "system"


def test_user_bin_root_uses_local_bin_by_default(tmp_path):
    home = tmp_path / "home"

    assert (
        bin_root(
            environ={},
            platform="linux",
            home=home,
        )
        == home / ".local" / "bin"
    )


def test_system_bin_root_uses_usr_local_bin_by_default(tmp_path):
    assert (
        bin_root(
            system=True,
            environ={},
            platform="linux",
            home=tmp_path / "home",
        ).as_posix()
        == "/usr/local/bin"
    )


def test_bin_root_accepts_explicit_semantic_override(tmp_path):
    user = tmp_path / "user-bin"
    system = tmp_path / "system-bin"

    assert bin_root(bin_dir=user, platform="linux") == user
    assert bin_root(system=True, bin_dir=system, platform="linux") == system



def test_gateway_resolves_legacy_path_environment_as_semantic_bindings(
    tmp_path,
    monkeypatch,
):
    from gway import Gateway

    user_data = tmp_path / "user-data"
    user_bin = tmp_path / "user-bin"
    system_data = tmp_path / "system-data"
    system_bin = tmp_path / "system-bin"
    monkeypatch.setenv("GWAY_DATA_DIR", str(user_data))
    monkeypatch.setenv("GWAY_BIN_DIR", str(user_bin))
    monkeypatch.setenv("GWAY_SYSTEM_DATA_DIR", str(system_data))
    monkeypatch.setenv("GWAY_SYSTEM_BIN_DIR", str(system_bin))

    gateway = Gateway()

    assert gateway.data_root() == user_data
    assert gateway.bin_root() == user_bin
    assert gateway.data_root(system=True) == system_data
    assert gateway.bin_root(system=True) == system_bin
