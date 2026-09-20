from types import SimpleNamespace

from gway.config import load_project_main_packages
from gway.gateway import Gateway
from gway.souschef.discovery import discover


def test_sous_chef_jobs_are_discovered_from_pyproject(tmp_path):
    recipe = tmp_path / "nightly.rx"
    recipe.write_text("", encoding="utf-8")
    manifest = tmp_path / "pyproject.toml"
    manifest.write_text(
        '[project]\n'
        'name = "demo"\n'
        '[tool.gway.sous-chef.nightly]\n'
        'recipe = "nightly.rx"\n'
        'every = "15m"\n',
        encoding="utf-8",
    )

    runtime = SimpleNamespace()
    jobs = discover(runtime, (), local_manifest=manifest)

    job = jobs[("demo", "nightly")]
    assert job.recipe == recipe.resolve()
    assert job.every == 900.0


def test_sous_chef_ignores_legacy_gway_toml(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\n',
        encoding="utf-8",
    )
    (tmp_path / "gway.toml").write_text(
        '[project]\n'
        'name = "demo"\n'
        '[sous-chef.legacy]\n'
        'recipe = "legacy.rx"\n',
        encoding="utf-8",
    )

    runtime = SimpleNamespace()
    jobs = discover(
        runtime,
        (),
        local_manifest=tmp_path / "pyproject.toml",
    )

    assert jobs == {}


def test_package_main_launchable_keeps_project_ownership(tmp_path):
    package = tmp_path / "worker"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "__main__.py").write_text(
        'VALUE = 1\n',
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\n',
        encoding="utf-8",
    )

    runtime = Gateway()
    load_project_main_packages(runtime, tmp_path, "demo")

    launchable = runtime.launchables["worker"]
    assert launchable.root == tmp_path.resolve()
    assert launchable.metadata["project"] == "demo"
