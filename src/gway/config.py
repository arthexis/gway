from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from ._toml import tomllib


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class GwayPaths:
    config_dir: Path
    data_dir: Path

    @property
    def config_file(self) -> Path:
        return self.config_dir / "config.toml"

    @property
    def state_file(self) -> Path:
        return self.data_dir / "state.json"

    @property
    def projects_dir(self) -> Path:
        return self.data_dir / "projects"

    @property
    def environments_dir(self) -> Path:
        return self.data_dir / "environments"


@dataclass(frozen=True)
class GwayConfig:
    trusted_owners: tuple[str, ...] = ("arthexis",)


def default_paths(
    env: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> GwayPaths:
    values = os.environ if env is None else env
    home_dir = Path.home() if home is None else Path(home)

    if values.get("GWAY_CONFIG_HOME"):
        config_dir = Path(values["GWAY_CONFIG_HOME"]).expanduser()
    elif os.name == "nt":
        config_root = Path(values.get("APPDATA") or home_dir / "AppData" / "Roaming")
        config_dir = config_root / "gway"
    else:
        config_root = Path(values.get("XDG_CONFIG_HOME") or home_dir / ".config")
        config_dir = config_root / "gway"

    if values.get("GWAY_DATA_HOME"):
        data_dir = Path(values["GWAY_DATA_HOME"]).expanduser()
    elif os.name == "nt":
        data_root = Path(values.get("LOCALAPPDATA") or home_dir / "AppData" / "Local")
        data_dir = data_root / "gway"
    else:
        data_root = Path(values.get("XDG_DATA_HOME") or home_dir / ".local" / "share")
        data_dir = data_root / "gway"

    return GwayPaths(config_dir=config_dir, data_dir=data_dir)


def load_config(paths: GwayPaths | None = None) -> GwayConfig:
    active_paths = paths or default_paths()
    path = active_paths.config_file
    if not path.exists():
        return GwayConfig()

    try:
        with path.open("rb") as stream:
            data = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"cannot read GWAY config {path}: {exc}") from exc

    github = data.get("github", {})
    if not isinstance(github, dict):
        raise ConfigError("[github] must be a table")
    owners = github.get("owners", ["arthexis"])
    if (
        not isinstance(owners, list)
        or not owners
        or not all(isinstance(owner, str) and owner.strip() for owner in owners)
    ):
        raise ConfigError("[github].owners must be a non-empty array of strings")

    return GwayConfig(trusted_owners=tuple(owner.strip() for owner in owners))
