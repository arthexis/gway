import subprocess
from pathlib import Path

import pytest

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


def _commit_checkout(checkout: Path) -> None:
    subprocess.run(["git", "-C", str(checkout), "init", "--quiet"], check=True)
    subprocess.run(
        ["git", "-C", str(checkout), "config", "user.email", "tests@example.invalid"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(checkout), "config", "user.name", "Gway Tests"],
        check=True,
    )
    subprocess.run(["git", "-C", str(checkout), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(checkout), "commit", "--quiet", "-m", "fixture"],
        check=True,
    )


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
        _commit_checkout(self.target)
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
        assert (checkout / ".git").is_dir()

    def upgrade(self, checkout: Path, full_name: str) -> str:
        self.events.append("upgrade")
        assert checkout == self.target
        assert full_name == self.repository.full_name
        assert not (checkout / "removed-command.py").exists()
        (checkout / "gway.toml").write_text(
            _manifest(self.root / "managed", "new"), encoding="utf-8"
        )
        return "new-revision"

    def reset(self, checkout: Path, full_name: str, revision: str) -> None:
        self.events.append("reset")
        assert checkout == self.target
        assert full_name == self.repository.full_name
        assert revision == "old-revision"
        (checkout / "gway.toml").write_text(
            _manifest(self.root / "managed", "old"), encoding="utf-8"
        )
        (checkout / "removed-command.py").write_text("obsolete\n", encoding="utf-8")

    def revision(self, checkout: Path) -> str:
        return (
            "new-revision"
            if "new" in (checkout / "gway.toml").read_text()
            else "old-revision"
        )


class ReinstallRunner:
    def __init__(
        self,
        root: Path,
        events: list[str],
        *,
        fail_refresh: bool = False,
    ) -> None:
        self.root = root
        self.events = events
        self.fail_refresh = fail_refresh

    def refresh(self, project, arguments=()):
        if project.aliases == ("old",):
            self.events.append("rollback-refresh")
            assert (project.path / "removed-command.py").exists()
        else:
            self.events.append("refresh")
            assert not (project.path / "removed-command.py").exists()
            assert project.aliases == ("new",)
            if self.fail_refresh:
                raise RuntimeError("refresh failed")
        environment = self.root / "managed" / ".venv"
        environment.mkdir(parents=True, exist_ok=True)
        return environment

    def prepare(self, project, arguments=()):
        raise AssertionError("existing managed installs must refresh, not prepare")

    def run_lifecycle(self, project, operation: str, arguments=()):
        self.events.append(f"lifecycle:{operation}")


def test_reinstall_refreshes_existing_checkout_before_environment_and_lifecycle(
    tmp_path: Path,
) -> None:
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


def test_reinstall_rolls_back_checkout_and_environment_when_refresh_fails(
    tmp_path: Path,
) -> None:
    events: list[str] = []
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    repositories = ReinstallRepositories(tmp_path, events)
    runner = ReinstallRunner(tmp_path, events, fail_refresh=True)
    installer = Installer(Registry(paths), repositories=repositories, runner=runner)

    with pytest.raises(RuntimeError, match="refresh failed"):
        installer.install("fixture")

    assert events == ["upgrade", "refresh", "reset", "rollback-refresh"]
    assert repositories.revision(repositories.target) == "old-revision"
    assert (repositories.target / "removed-command.py").exists()
