import sys
from pathlib import Path

from gway.config import GwayPaths
from gway.dispatcher import Dispatcher
from gway.install import Installer
from gway.registry import Registry
from gway.repository import ResolvedRepository


class FixtureRepositories:
    def __init__(self, root: Path) -> None:
        self.root = root

    def resolve(self, spec: str) -> ResolvedRepository:
        assert spec == "fixture"
        return ResolvedRepository("arthexis", "gway-fixture")

    def clone(self, repository: ResolvedRepository) -> Path:
        checkout = self.root / "data" / "projects" / repository.owner / repository.name
        package = checkout / "src" / "fixture_project"
        package.mkdir(parents=True)
        (checkout / "gway.toml").write_text(
            """[project]
name = "fixture"
aliases = ["fx"]

[adapter]
type = "python"
module = "fixture_project.gway"
""",
            encoding="utf-8",
        )
        (package / "__init__.py").write_text("", encoding="utf-8")
        (package / "gway.py").write_text(
            """def status() -> str:
    import fixture_dependency

    return fixture_dependency.VALUE
""",
            encoding="utf-8",
        )
        return checkout

    def revision(self, checkout: Path) -> str:
        return "0123456789abcdef"


class FixtureRunner:
    def __init__(self, paths: GwayPaths) -> None:
        self.paths = paths

    def environment_path(self, project) -> Path:
        return self.paths.environments_dir / project.name

    def prepare(self, project) -> Path:
        environment = self.environment_path(project)
        if sys.platform == "win32":
            site_packages = environment / "Lib" / "site-packages"
        else:
            version = f"python{sys.version_info.major}.{sys.version_info.minor}"
            site_packages = environment / "lib" / version / "site-packages"
        site_packages.mkdir(parents=True)
        (site_packages / "fixture_dependency.py").write_text(
            'VALUE = "installed-ok"\n',
            encoding="utf-8",
        )
        return environment


def test_install_records_state_and_dispatches_immediately(tmp_path: Path) -> None:
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    registry = Registry(paths)
    installer = Installer(
        registry,
        repositories=FixtureRepositories(tmp_path),
        runner=FixtureRunner(paths),
    )

    project = installer.install("fixture")

    assert project.repository == "arthexis/gway-fixture"
    assert project.revision == "0123456789abcdef"
    assert project.environment == paths.environments_dir / "fixture"
    assert registry.require("fx") == project
    assert Dispatcher(registry).run("fixture", ["status"]) == "installed-ok"
