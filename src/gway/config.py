from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GwayPaths:
    config_dir: Path
    data_dir: Path

    @property
    def state_file(self) -> Path:
        return self.data_dir / "state.json"


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
