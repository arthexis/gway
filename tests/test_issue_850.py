from pathlib import Path

from gway.config import GwayPaths
from gway.project import Project
from gway.registry import Registry
from gway.upgrade import Upgrader


MANIFEST = """[project]
name = "fixture"

[adapter]
type = "python"
module = "fixture.gway"
"""


class Repositories:
    def __init__(self) -> None:
        self.current_revision = "old-revision"

    def upgrade(self, checkout: Path, full_name: str, *, force: bool = False) -> str:
        del checkout, full_name, force
        self.current_revision = "upgrade-returned-revision"
        return self.current_revision

    def revision(self, checkout: Path) -> str:
        del checkout
        return self.current_revision


class Runner:
    def __init__(self, repositories: Repositories) -> None:
        self.repositories = repositories

    def refresh(self, project: Project) -> Path | None:
        # Simulate the checkout moving again while post-upgrade preparation runs.
        self.repositories.current_revision = "actual-final-revision"
        return project.environment


def test_upgrade_registers_actual_final_checkout_revision(tmp_path: Path) -> None:
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    registry = Registry(paths)
    checkout = tmp_path / "fixture"
    checkout.mkdir()
    (checkout / "gway.toml").write_text(MANIFEST, encoding="utf-8")
    registry.register(
        Project(
            name="fixture",
            path=checkout,
            adapter_type="python",
            adapter_config={"module": "fixture.gway"},
            repository="arthexis/fixture",
            revision="old-revision",
        )
    )
    repositories = Repositories()

    result = Upgrader(
        registry,
        repositories=repositories,
        runner=Runner(repositories),
    ).project_result("fixture")

    assert result.project.revision == "actual-final-revision"
    assert registry.require("fixture").revision == "actual-final-revision"
