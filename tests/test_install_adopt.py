from pathlib import Path
from types import SimpleNamespace

import gway.cli as cli
import gway.install as install_module
from gway.config import GwayPaths
from gway.install import AdoptionPreview, Installer
from gway.registry import Registry
from gway.repository import ResolvedRepository


class _PreviewInstaller:
    calls: list[tuple[object, ...]] = []

    def __init__(self, registry) -> None:
        self.registry = registry

    def preview_adoption(self, spec, source, *, arguments=()):
        self.calls.append((spec, source, tuple(arguments)))
        return AdoptionPreview(
            name="demo",
            source=Path(source),
            target=Path("/opt/demo/app"),
            revision="0123456789abcdef",
        )


def test_install_adopt_dry_run_routes_to_preflight(monkeypatch, tmp_path, capsys) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _PreviewInstaller.calls = []
    monkeypatch.setattr(cli, "Installer", _PreviewInstaller)

    dispatcher = SimpleNamespace(registry=object())
    result = cli.main(
        ["install", "demo", "--adopt", "--from", str(source), "--dry-run"],
        dispatcher=dispatcher,
    )

    assert result == 0
    assert _PreviewInstaller.calls == [
        (
            "demo",
            str(source),
            ("--adopt", "--from", str(source), "--dry-run"),
        )
    ]
    output = capsys.readouterr().out
    assert "status: preflight" in output
    assert "source:" in output
    assert "target: /opt/demo/app" in output


def test_install_adopt_execution_is_refused_before_install(monkeypatch, tmp_path, capsys) -> None:
    source = tmp_path / "source"
    source.mkdir()

    class FailingInstaller:
        def __init__(self, registry) -> None:
            raise AssertionError("installer must not be constructed")

    monkeypatch.setattr(cli, "Installer", FailingInstaller)
    dispatcher = SimpleNamespace(registry=object())

    result = cli.main(
        ["install", "demo", "--adopt", "--from", str(source)],
        dispatcher=dispatcher,
    )

    assert result == 2
    assert "not available yet" in capsys.readouterr().err


class _Repositories:
    def __init__(self, target: Path) -> None:
        self.target = target
        self.clone_destination: Path | None = None

    def resolve(self, spec: str) -> ResolvedRepository:
        assert spec == "demo"
        return ResolvedRepository("arthexis", "demo")

    def clone(self, repository: ResolvedRepository, destination: Path | None = None) -> Path:
        assert destination is not None
        self.clone_destination = destination
        destination.mkdir(parents=True)
        (destination / "gway.toml").write_text(
            f'''[project]
name = "demo"

[adapter]
type = "python"
module = "demo"

[install]
root = "{self.target}"
checkout = "app"
environment = ".venv"

[lifecycle]
install = "demo.lifecycle:install"
''',
            encoding="utf-8",
        )
        return destination

    def revision(self, checkout: Path) -> str:
        return "0123456789abcdef"


class _Runner:
    calls: list[tuple[object, ...]] = []

    def __init__(self, paths: GwayPaths) -> None:
        self.paths = paths

    def prepare(self, project, *, arguments=()):
        assert project.install_layout is None
        environment = self.paths.environments_dir / project.name
        environment.mkdir(parents=True)
        self.calls.append(("prepare", tuple(arguments)))
        return environment

    def run_lifecycle(self, project, action: str, arguments=()):
        assert project.install_layout is None
        assert project.environment is not None and project.environment.exists()
        self.calls.append(("hook", action, tuple(arguments)))


def test_preview_adoption_does_not_touch_source_target_or_registry(
    monkeypatch, tmp_path
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    sentinel = source / "developer.txt"
    sentinel.write_text("unchanged", encoding="utf-8")
    target = tmp_path / "managed"
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    registry = Registry(paths)
    repositories = _Repositories(target)
    _Runner.calls = []
    monkeypatch.setattr(install_module, "Runner", _Runner)

    preview = Installer(registry, repositories=repositories).preview_adoption(
        "demo",
        source,
        arguments=("--adopt", "--from", str(source), "--dry-run"),
    )

    assert preview.source == source.resolve()
    assert preview.target == target / "app"
    assert preview.revision == "0123456789abcdef"
    assert sentinel.read_text(encoding="utf-8") == "unchanged"
    assert not target.exists()
    assert registry.list() == []
    assert repositories.clone_destination is not None
    assert not repositories.clone_destination.exists()
    assert _Runner.calls == [
        ("prepare", ("--adopt", "--from", str(source), "--dry-run")),
        ("hook", "install", ("--adopt", "--from", str(source), "--dry-run")),
    ]
