from __future__ import annotations

from pathlib import Path

import pytest

from gway.config import GwayPaths
from gway.dispatcher.errors import DispatchError
from gway.logs.consumers import canonical_consumers, consumer_identity, normalize_consumers
from gway.logs.state import read_state, state_lock, state_path, write_state
from gway.project import Project


def _paths(tmp_path: Path) -> GwayPaths:
    return GwayPaths(config_dir=tmp_path / "config", data_dir=tmp_path / "data")


def _project(tmp_path: Path) -> Project:
    return Project(
        name="wire",
        path=tmp_path / "wire",
        adapter_type="python",
        adapter_config={},
        aliases=("gway-wire",),
    )


def test_consumer_normalization_is_safe_and_case_insensitive() -> None:
    assert normalize_consumers(("wire, Arthexis", "WIRE")) == ("wire", "Arthexis")
    with pytest.raises(DispatchError, match="invalid log consumer"):
        normalize_consumers(("../wire",))


def test_consumer_identity_resolves_project_aliases(tmp_path: Path) -> None:
    project = _project(tmp_path)

    def resolve(value: str) -> Project | None:
        return project if value.casefold() in {"wire", "gway-wire"} else None

    name, identities = consumer_identity("gway-wire", resolve)
    canonical, combined = canonical_consumers(("gway-wire", "wire"), resolve)

    assert name == "wire"
    assert identities == {"wire", "gway-wire"}
    assert canonical == ("wire",)
    assert combined == {"wire", "gway-wire"}


def test_logging_state_round_trips_under_lock(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    payload = {
        "version": 1,
        "bindings": {
            "https://logs.example.test": {
                "provider": "fixture",
                "consumers": ["wire"],
            }
        },
    }

    with state_lock(paths):
        write_state(paths, payload)

    assert state_path(paths) == paths.data_dir / "log-consumers.json"
    assert read_state(paths) == payload
    assert oct(state_path(paths).stat().st_mode & 0o777) == "0o600"
