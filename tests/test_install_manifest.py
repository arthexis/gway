from pathlib import Path

import pytest

from gway.config import GwayPaths
from gway.project import InstallLayout, LifecycleHooks, ManifestError, Project
from gway.registry import Registry


def write_manifest(root: Path, extra: str = "") -> Path:
    root.mkdir()
    (root / "gway.toml").write_text(
        f'''[project]\nname = "arthexis"\n\n[adapter]\ntype = "django"\nmanage = "manage.py"\n{extra}\n''',
        encoding="utf-8",
    )
    return root


def test_install_layout_and_lifecycle_hooks_are_loaded(tmp_path: Path) -> None:
    project = Project.from_path(
        write_manifest(
            tmp_path / "project",
            '''\n[install]\nroot = "/opt/arthexis"\ncheckout = "app"\nenvironment = ".venv"\n\n[lifecycle]\ninstall = "apps.core.system.lifecycle:install"\nupgrade = "apps.core.system.lifecycle:upgrade"\n''',
        )
    )

    assert project.install_layout == InstallLayout(
        root=Path("/opt/arthexis"),
        checkout=Path("/opt/arthexis/app"),
        environment=Path("/opt/arthexis/.venv"),
    )
    assert project.lifecycle_hooks == LifecycleHooks(
        install="apps.core.system.lifecycle:install",
        upgrade="apps.core.system.lifecycle:upgrade",
    )


def test_install_and_lifecycle_are_optional_for_existing_projects(tmp_path: Path) -> None:
    project = Project.from_path(write_manifest(tmp_path / "project"))

    assert project.install_layout is None
    assert project.lifecycle_hooks is None


def test_registry_round_trips_install_contract(tmp_path: Path) -> None:
    project_root = write_manifest(
        tmp_path / "project",
        '''\n[install]\nroot = "/opt/arthexis"\ncheckout = "app"\nenvironment = ".venv"\n\n[lifecycle]\ninstall = "apps.core.system.lifecycle:install"\nupgrade = "apps.core.system.lifecycle:upgrade"\n''',
    )
    registry = Registry(GwayPaths(tmp_path / "config", tmp_path / "data"))

    registered = registry.register_path(project_root)
    reloaded = Registry(registry.paths).require("arthexis")

    assert reloaded == registered
    assert reloaded.install_layout is not None
    assert reloaded.install_layout.checkout == Path("/opt/arthexis/app")
    assert reloaded.lifecycle_hooks is not None
    assert reloaded.lifecycle_hooks.upgrade == "apps.core.system.lifecycle:upgrade"


def test_install_root_must_be_absolute(tmp_path: Path) -> None:
    root = write_manifest(
        tmp_path / "project",
        '''\n[install]\nroot = "var/arthexis"\ncheckout = "app"\nenvironment = ".venv"\n''',
    )

    with pytest.raises(ManifestError, match=r"\[install\]\.root.*absolute"):
        Project.from_path(root)


@pytest.mark.parametrize("field", ["checkout", "environment"])
def test_install_children_must_stay_within_root(tmp_path: Path, field: str) -> None:
    checkout = '"../app"' if field == "checkout" else '"app"'
    environment = '"../venv"' if field == "environment" else '".venv"'
    root = write_manifest(
        tmp_path / "project",
        f'''\n[install]\nroot = "/opt/arthexis"\ncheckout = {checkout}\nenvironment = {environment}\n''',
    )

    with pytest.raises(ManifestError, match=rf"\[install\]\.{field}.*root"):
        Project.from_path(root)


def test_install_requires_all_layout_fields(tmp_path: Path) -> None:
    root = write_manifest(
        tmp_path / "project",
        '''\n[install]\nroot = "/opt/arthexis"\ncheckout = "app"\n''',
    )

    with pytest.raises(ManifestError, match=r"\[install\]\.environment"):
        Project.from_path(root)


@pytest.mark.parametrize(
    "reference",
    [
        "apps.core.system.lifecycle.install",
        "apps.core.system.lifecycle:",
        ":install",
        "apps/core/system/lifecycle:install",
    ],
)
def test_lifecycle_hooks_require_module_function_references(
    tmp_path: Path, reference: str
) -> None:
    root = write_manifest(
        tmp_path / "project",
        f'''\n[lifecycle]\ninstall = "{reference}"\n''',
    )

    with pytest.raises(ManifestError, match="module:function"):
        Project.from_path(root)


def test_lifecycle_may_declare_only_one_hook(tmp_path: Path) -> None:
    project = Project.from_path(
        write_manifest(
            tmp_path / "project",
            '''\n[lifecycle]\nupgrade = "example.lifecycle:upgrade"\n''',
        )
    )

    assert project.lifecycle_hooks == LifecycleHooks(upgrade="example.lifecycle:upgrade")


def test_empty_lifecycle_table_is_rejected(tmp_path: Path) -> None:
    root = write_manifest(tmp_path / "project", "\n[lifecycle]\n")

    with pytest.raises(ManifestError, match="install and/or upgrade"):
        Project.from_path(root)
