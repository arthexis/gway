from pathlib import Path

from gway.config import GwayPaths, default_paths, load_config


def test_empty_xdg_roots_fall_back_to_home(tmp_path: Path) -> None:
    paths = default_paths(
        env={"XDG_CONFIG_HOME": "", "XDG_DATA_HOME": ""},
        home=tmp_path,
    )

    assert paths.config_dir == tmp_path / ".config" / "gway"
    assert paths.data_dir == tmp_path / ".local" / "share" / "gway"


def test_load_config_reads_trusted_github_owners(tmp_path: Path) -> None:
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    paths.config_dir.mkdir()
    paths.config_file.write_text(
        '[github]\nowners = [" arthexis ", "example"]\n',
        encoding="utf-8",
    )

    config = load_config(paths)

    assert config.trusted_owners == ("arthexis", "example")
    assert paths.projects_dir == tmp_path / "data" / "projects"
    assert paths.environments_dir == tmp_path / "data" / "environments"
