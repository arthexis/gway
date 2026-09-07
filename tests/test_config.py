from pathlib import Path

from gway.config import default_paths


def test_empty_xdg_roots_fall_back_to_home(tmp_path: Path) -> None:
    paths = default_paths(
        env={"XDG_CONFIG_HOME": "", "XDG_DATA_HOME": ""},
        home=tmp_path,
    )

    assert paths.config_dir == tmp_path / ".config" / "gway"
    assert paths.data_dir == tmp_path / ".local" / "share" / "gway"
