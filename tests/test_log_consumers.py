from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from gway.config import GwayPaths
from gway.dispatcher.errors import DispatchError
from gway.log_command import run_log
from gway.log_consumers import configure_consumers, consumer_environment_file
from gway.logging import current_context
from gway.project import Project
from gway.service import ServiceManager


def _paths(tmp_path: Path) -> GwayPaths:
    return GwayPaths(config_dir=tmp_path / "config", data_dir=tmp_path / "data")


@pytest.fixture(autouse=True)
def _isolate_consumer_logging_environment(monkeypatch):
    # Consumer activation intentionally updates os.environ so reload/exec inherits
    # the credential. Make that process-level behavior test-local.
    monkeypatch.delenv("GWAY_LOG_DESTINATION", raising=False)
    monkeypatch.delenv("GWAY_LOG_TOKEN", raising=False)


class FakeWeb:
    def __init__(self) -> None:
        self.issued = 0
        self.token_id = "local-ingest"
        self.token = "gweb_v1_local-ingest_secret"
        self.revoked = False

    def dispatch(self, project: str, tokens) -> object:
        assert project == "web"
        assert tokens[0] == "token"
        if "--list" in tokens:
            return [
                {
                    "token_id": self.token_id,
                    "expires_at": (
                        datetime.now(timezone.utc) + timedelta(days=30)
                    ).isoformat(),
                    "revoked_at": datetime.now(timezone.utc).isoformat()
                    if self.revoked
                    else None,
                }
            ]
        self.issued += 1
        assert tokens[tokens.index("--scope") + 1] == "logs:ingest"
        return {"token_id": self.token_id, "token": self.token}


def test_log_plural_consumers_accepts_csv_and_singular_accepts_one(
    tmp_path: Path, monkeypatch
) -> None:
    paths = _paths(tmp_path)
    web = FakeWeb()
    monkeypatch.setenv("GWAY_LOG_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("GWAY_RUN_ID", "test-log-consumers")

    state = run_log(
        [
            "--to",
            "https://logs.example.test",
            "--consumer",
            "wire",
            "--consumers",
            "arthexis,epaper",
        ],
        dispatch=web.dispatch,
        paths=paths,
    )

    assert state["consumers"] == ["wire", "arthexis", "epaper"]
    assert state["consumer_destination"] == "https://logs.example.test"
    assert state["consumer_token_id"] == web.token_id
    assert web.issued == 1
    for consumer in ("wire", "arthexis", "epaper"):
        environment = paths.data_dir / "log-consumers" / f"{consumer}.env"
        assert environment.is_file()
        assert oct(environment.stat().st_mode & 0o777) == "0o600"
        text = environment.read_text(encoding="utf-8")
        assert "GWAY_LOG_DESTINATION=\"https://logs.example.test\"" in text
        assert f'GWAY_LOG_TOKEN="{web.token}"' in text


def test_singular_consumer_rejects_csv(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GWAY_RUN_ID", "test-log-singular-consumer")
    with pytest.raises(DispatchError, match="--consumer accepts one consumer"):
        run_log(
            ["--to", "https://logs.example.test", "--consumer", "wire,arthexis"],
            dispatch=FakeWeb().dispatch,
            paths=_paths(tmp_path),
        )


def test_consumer_binding_reuses_live_local_token(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    web = FakeWeb()

    first = configure_consumers(
        ["wire"],
        ["https://logs.example.test"],
        dispatch=web.dispatch,
        paths=paths,
    )
    second = configure_consumers(
        ["arthexis"],
        ["https://logs.example.test"],
        dispatch=web.dispatch,
        paths=paths,
    )

    assert first["token_id"] == second["token_id"] == web.token_id
    assert second["consumers"] == ["wire", "arthexis"]
    assert web.issued == 1


def test_consumer_binding_rotates_revoked_token(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    web = FakeWeb()
    configure_consumers(
        ["wire"],
        ["https://logs.example.test"],
        dispatch=web.dispatch,
        paths=paths,
    )
    web.revoked = True
    web.token_id = "replacement"
    web.token = "gweb_v1_replacement_secret"

    result = configure_consumers(
        ["wire"],
        ["https://logs.example.test"],
        dispatch=web.dispatch,
        paths=paths,
    )

    assert result["token_id"] == "replacement"
    assert web.issued == 2


def test_consumer_environment_matches_project_alias(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    web = FakeWeb()
    configure_consumers(
        ["gway-wire"],
        ["https://logs.example.test"],
        dispatch=web.dispatch,
        paths=paths,
    )
    project = Project(
        name="wire",
        path=tmp_path / "wire",
        adapter_type="python",
        adapter_config={"module": "wire"},
        aliases=("gway-wire",),
    )

    environment = consumer_environment_file(project, paths=paths)

    assert environment == paths.data_dir / "log-consumers" / "gway-wire.env"


def test_service_render_injects_private_consumer_environment(
    tmp_path: Path, monkeypatch
) -> None:
    paths = _paths(tmp_path)
    monkeypatch.setenv("GWAY_DATA_HOME", str(paths.data_dir))
    web = FakeWeb()
    configure_consumers(
        ["wire"],
        ["https://logs.example.test"],
        dispatch=web.dispatch,
        paths=paths,
    )
    project_path = tmp_path / "wire"
    project_path.mkdir()
    (project_path / "gway.toml").write_text(
        """[project]
name = "wire"

[adapter]
type = "python"
module = "wire"

[service]
command = ["/bin/true"]
""",
        encoding="utf-8",
    )
    project = Project.from_path(project_path)

    rendered = ServiceManager(project, unit_directory=tmp_path / "systemd").render(user="root")

    expected = paths.data_dir / "log-consumers" / "wire.env"
    assert f'EnvironmentFile="{expected}"' in rendered
    assert web.token not in rendered


def test_managed_service_destination_seeds_new_log_context(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GWAY_LOG_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("GWAY_RUN_ID", "test-service-log-default")
    monkeypatch.setenv("GWAY_LOG_DESTINATION", "https://logs.example.test")
    monkeypatch.delenv("GWAY_LOG_CONTEXT", raising=False)

    state = current_context()

    assert state["to"] == ["https://logs.example.test"]


def test_consumer_names_are_safe_for_environment_paths(tmp_path: Path) -> None:
    with pytest.raises(DispatchError, match="invalid log consumer"):
        configure_consumers(
            ["../wire"],
            ["https://logs.example.test"],
            dispatch=FakeWeb().dispatch,
            paths=_paths(tmp_path),
        )
