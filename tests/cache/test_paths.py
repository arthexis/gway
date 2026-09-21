from gway.cache import default_root


def test_cache_override_wins_on_every_platform(tmp_path):
    override = tmp_path / "shared-cache"

    assert (
        default_root(
            environ={"GWAY_CACHE_DIR": str(override)},
            platform="linux",
            home=tmp_path / "home",
        )
        == override
    )


def test_linux_cache_uses_xdg_cache_home(tmp_path):
    base = tmp_path / "xdg"

    assert (
        default_root(
            environ={"XDG_CACHE_HOME": str(base)},
            platform="linux",
            home=tmp_path / "home",
        )
        == base / "gway"
    )


def test_linux_cache_falls_back_to_home_cache(tmp_path):
    home = tmp_path / "home"

    assert (
        default_root(
            environ={},
            platform="linux",
            home=home,
        )
        == home / ".cache" / "gway"
    )


def test_macos_cache_uses_library_caches(tmp_path):
    home = tmp_path / "home"

    assert (
        default_root(
            environ={},
            platform="darwin",
            home=home,
        )
        == home / "Library" / "Caches" / "gway"
    )


def test_windows_cache_uses_local_app_data(tmp_path):
    base = tmp_path / "LocalAppData"

    assert (
        default_root(
            environ={"LOCALAPPDATA": str(base)},
            platform="win32",
            home=tmp_path / "home",
        )
        == base / "gway" / "cache"
    )
