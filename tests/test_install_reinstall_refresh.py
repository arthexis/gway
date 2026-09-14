from pathlib import Path

from gway.config import GwayPaths
from gway.install import Installer
from gway.registry import Registry
from gway.repository import ResolvedRepository


def _manifest(root: Path, alias: str) -> str:
    return f'''[project]
name = "fixture"
aliases = ["{alias}"]

[adapter]
type = "python"
module = "fixture_project.gway"

[install]
root = "{root.as_posix()}"
checkout = "app"
environment = ".venv"
'''


class ReinstallRepositories:
    def __init__(self, root: Path, events: list[str]) -> None:
        self.root = root
        self.events = events
        self.repository = ResolvedRepository("arthexis", "gway-fixture")
        self.target = root / "managed" / "app"
        self.target.mkdir(parents=True)
        (self.target / "gway.toml").write_text(
            _manifest(root / "managed", "old"), encoding="utf-8"
        )
        stale = self.target / "removed-command.py"
        stale.write_text("obsolete\n", encoding="utf-8")

    def resolve(self, spec: str) -> ResolvedRepository:
        assert spec == "fixture"
        return self.repository

    def clone(self, repository: ResolvedRepository) -> Path:
        checkout = self.root / "staging" / "gway-fixture"
        package = checkout / "src" / "fixture_project"
        package.mkdir(parents=True)
        (checkout / "gway.toml").write_text(
            _manifest(self.root / "managed", "new"), encoding="utf-8"
        )
        (package / "__init__.py").write_text("", encoding="utf-8")
        (package / "gway.py").write_text("def status(): return 'ok'\n", encoding="utf-8")
        return checkout

    def validate_checkout(self, checkout: Path, full_name: str) -> None:
        assert checkout == self.target
        assert full_name == self.repository.full_name

    def upgrade(self, checkout: Path, full_name: str) -> str:
        self.events.append("upgrade")
        assert checkout == self.target
        assert full_name == self.repository.full_name
        (checkout / "removed-command.py").unlink()
        (checkout / "gway.toml").write_text(
            _manifest(self.root / "managed", "new"), encoding="utf-8"
        )
        return "new-revision"

    def revision(self, checkout: Path) -> str:
        return "new-revision" if "new" in (checkout / "gway.toml").read_text() else "old-revision"


class ReinstallRunner:
    def __init__(self, root: Path, events: list[str]) -> None:
        self.root = root
        self.events = events

    def refresh(self, project, arguments=()):
        self.events.append("refresh")
        assert not (project.path / "removed-command.py").exists()
        assert project.aliases == ("new",)
        environment = self.root / "managed" / ".venv"
        environment.mkdir(parents=True, exist_ok=True)
        return environment

    def prepare(self, project, arguments=()):
        raise AssertionError("existing managed installs must refresh, not prepare")

    def run_lifecycle(self, project, operation: str, arguments=()):
        self.events.append(f"lifecycle:{operation}")


def test_reinstall_refreshes_existing_checkout_before_environment_and_lifecycle(tmp_path: Path) -> None:
    events: list[str] = []
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    repositories = ReinstallRepositories(tmp_path, events)
    runner = ReinstallRunner(tmp_path, events)
    installer = Installer(Registry(paths), repositories=repositories, runner=runner)

    project = installer.install("fixture")

    assert events == ["upgrade", "refresh"]
    assert project.path == repositories.target
    assert project.revision == "new-revision"
    assert project.aliases == ("new",)
    assert not (repositories.target / "removed-command.py").exists()
