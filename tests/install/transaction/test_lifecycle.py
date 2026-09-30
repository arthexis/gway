import os
from pathlib import Path
import subprocess
import venv

import pytest

from gway.install import InstallRequest, InstallState, UninstallRequest
import gway.install.transaction as transaction
from gway.install.source import fingerprint
from gway.project import invoke_target


def _fake_product_runtime(project, selected):
    project = Path(project)
    environment = project / ".venv"
    venv.EnvBuilder(with_pip=False).create(environment)


def _product_python(project):
    return Path(project) / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def test_local_install_stages_copy_and_records_managed_project(
    make_project,
    managed_paths,
):
    source = make_project("wire")

    installed = transaction.install_local(
        InstallRequest(str(source)),
        paths=managed_paths,
    )

    destination = managed_paths.projects / "wire"
    assert installed.name == "wire"
    assert installed.source == str(source.resolve())
    assert installed.install_path == destination
    assert installed.fingerprint.startswith("sha256:")
    assert installed.installed_at is not None
    assert (destination / "pyproject.toml").is_file()
    assert (destination / "module.py").read_text(encoding="utf-8") == "VALUE = 1\n"
    assert InstallState(managed_paths.state).get("wire") == installed


def test_local_install_does_not_modify_source_tree(
    make_project,
    managed_paths,
):
    source = make_project()
    before = sorted(path.relative_to(source).as_posix() for path in source.rglob("*"))

    transaction.install_local(
        InstallRequest(str(source)),
        paths=managed_paths,
    )

    after = sorted(path.relative_to(source).as_posix() for path in source.rglob("*"))
    assert after == before
    assert source != managed_paths.projects / "demo"


def test_repeated_unchanged_local_install_is_noop(
    make_project,
    managed_paths,
):
    source = make_project("wire")
    request = InstallRequest(str(source))

    first = transaction.install_local(request, paths=managed_paths)
    second = transaction.install_local(request, paths=managed_paths)

    assert second == first
    assert len(InstallState(managed_paths.state).all()) == 1


def test_repeated_unchanged_git_revision_is_noop_without_staging(
    make_project,
    managed_paths,
    monkeypatch,
):
    source = make_project("wire")
    request = InstallRequest("arthexis/wire", ref="main")
    identity = "https://github.com/arthexis/wire.git"

    first = transaction.install_materialized(
        request,
        source,
        source_identity=identity,
        requested_ref="main",
        resolved_revision="a" * 40,
        paths=managed_paths,
    )

    def unexpected_stage(*args, **kwargs):
        raise AssertionError("unchanged Git revision must not stage a replacement")

    monkeypatch.setattr(transaction, "_stage_project", unexpected_stage)

    second = transaction.install_materialized(
        request,
        source,
        source_identity=identity,
        requested_ref="main",
        resolved_revision="a" * 40,
        paths=managed_paths,
    )

    assert second == first
    assert InstallState(managed_paths.state).get("wire") == first


def test_changed_git_revision_updates_identity_without_replacing_identical_tree(
    make_project,
    managed_paths,
    monkeypatch,
):
    source = make_project("wire")
    request = InstallRequest("arthexis/wire", ref="main")
    identity = "https://github.com/arthexis/wire.git"

    first = transaction.install_materialized(
        request,
        source,
        source_identity=identity,
        requested_ref="main",
        resolved_revision="a" * 40,
        paths=managed_paths,
    )

    def unexpected_stage(*args, **kwargs):
        raise AssertionError("identical project tree does not need replacement")

    monkeypatch.setattr(transaction, "_stage_project", unexpected_stage)

    second = transaction.install_materialized(
        request,
        source,
        source_identity=identity,
        requested_ref="main",
        resolved_revision="b" * 40,
        paths=managed_paths,
    )

    assert second.resolved_revision == "b" * 40
    assert second.fingerprint == first.fingerprint
    assert second.install_path == first.install_path
    assert second.installed_at == first.installed_at
    assert InstallState(managed_paths.state).get("wire") == second


def test_changed_git_revision_and_tree_replaces_managed_project(
    make_project,
    managed_paths,
):
    source = make_project("wire")
    request = InstallRequest("arthexis/wire", ref="main")
    identity = "https://github.com/arthexis/wire.git"

    first = transaction.install_materialized(
        request,
        source,
        source_identity=identity,
        requested_ref="main",
        resolved_revision="a" * 40,
        paths=managed_paths,
    )
    destination = managed_paths.projects / "wire"
    assert (destination / "module.py").read_text(encoding="utf-8") == "VALUE = 1\n"

    (source / "module.py").write_text("VALUE = 2\n", encoding="utf-8")

    second = transaction.install_materialized(
        request,
        source,
        source_identity=identity,
        requested_ref="main",
        resolved_revision="b" * 40,
        paths=managed_paths,
    )

    assert second.resolved_revision == "b" * 40
    assert second.fingerprint != first.fingerprint
    assert second.install_path == first.install_path
    assert (destination / "module.py").read_text(encoding="utf-8") == "VALUE = 2\n"
    assert InstallState(managed_paths.state).get("wire") == second


def test_local_install_rejects_ref(make_project, managed_paths):
    source = make_project()

    with pytest.raises(ValueError, match="not supported for local"):
        transaction.install_local(
            InstallRequest(str(source), ref="main"),
            paths=managed_paths,
        )


def test_uninstall_removes_managed_copy_and_state_but_not_source(
    installed_project,
    managed_paths,
):
    removed = transaction.uninstall_local(
        UninstallRequest("wire"),
        paths=managed_paths,
    )

    assert removed == installed_project.installed
    assert installed_project.source.is_dir()
    assert not installed_project.destination.exists()
    assert installed_project.state.get("wire") is None


def test_uninstall_is_idempotent_when_project_is_absent(managed_paths):
    assert (
        transaction.uninstall_local(
            UninstallRequest("missing"),
            paths=managed_paths,
        )
        is None
    )
    assert not managed_paths.root.exists()


def test_uninstall_reconciles_stale_record_when_managed_copy_is_missing(
    installed_project,
    managed_paths,
):
    transaction._remove_path(installed_project.destination)

    removed = transaction.uninstall_local(
        UninstallRequest("wire"),
        paths=managed_paths,
    )

    assert removed == installed_project.installed
    assert installed_project.state.get("wire") is None


def test_project_install_does_not_touch_service_installation(
    make_project,
    managed_paths,
    monkeypatch,
):
    source = make_project("wire")

    def unexpected_backend(name):
        raise AssertionError("project install must not resolve service backends")

    monkeypatch.setattr("gway.install.service.get", unexpected_backend)

    installed = transaction.install_local(
        InstallRequest(str(source)),
        paths=managed_paths,
    )

    assert installed.name == "wire"
    assert installed.install_path.is_dir()


def test_install_recovery_restores_previous_project_when_launcher_rollback_fails(
    installed_project,
    managed_paths,
    monkeypatch,
):
    source = installed_project.source
    installed = installed_project.installed
    destination = installed_project.destination
    real_state = installed_project.state
    assert (destination / "module.py").read_text(encoding="utf-8") == "VALUE = 1\n"

    (source / "module.py").write_text("VALUE = 2\n", encoding="utf-8")

    class FailingState:
        def get(self, name, scope=None):
            return real_state.get(name, scope=scope)

        def put(self, record):
            raise OSError("state write failed")

        def remove(self, name, scope=None):
            return real_state.remove(name, scope=scope)

    class FailingLauncher:
        def rollback(self):
            raise RuntimeError("launcher rollback failed")

        def commit(self):
            raise AssertionError("failed install must not commit launchers")

    monkeypatch.setattr(
        transaction,
        "activate_project",
        lambda name, project, paths: FailingLauncher(),
    )

    with pytest.raises(OSError, match="state write failed") as raised:
        transaction.install_local(
            InstallRequest(str(source)),
            paths=managed_paths,
            state=FailingState(),
        )

    assert (destination / "module.py").read_text(encoding="utf-8") == "VALUE = 1\n"
    assert real_state.get("wire") == installed
    assert list(managed_paths.projects.glob(".wire.replace-*")) == []
    assert any(
        "launcher rollback" in note and "launcher rollback failed" in note
        for note in getattr(raised.value, "__notes__", ())
    )


def test_public_install_classifies_external_project_as_product(
    make_project,
    managed_paths,
    monkeypatch,
):
    from gway.install.ops import install

    monkeypatch.setattr(transaction, "_converge_product_runtime", _fake_product_runtime)
    source = make_project("arthexis", launcher=True)
    installed = install(source, paths=managed_paths)

    assert installed.kind == "product"
    assert installed.install_path == managed_paths.products / "arthexis"
    assert installed.install_path.is_dir()
    assert not (managed_paths.bin / "arthexis").exists()


def test_gway_project_remains_extension(make_project, managed_paths):
    from gway.install.ops import install

    source = make_project("gway")
    installed = install(source, paths=managed_paths)

    assert installed.kind == "extension"
    assert installed.install_path == managed_paths.projects / "gway"


def test_forced_kind_migration_replaces_matching_existing_product_target(
    make_project,
    managed_paths,
    monkeypatch,
):
    monkeypatch.setattr(transaction, "_converge_product_runtime", _fake_product_runtime)
    source = make_project("arthexis")
    extension = transaction.install_local(
        InstallRequest(str(source), kind="extension"),
        paths=managed_paths,
    )
    product = managed_paths.products / "arthexis"
    transaction._copy_project(source, product)
    (product / "module.py").write_text("VALUE = 0\n", encoding="utf-8")

    migrated = transaction.install_local(
        InstallRequest(str(source), kind="product", force=True),
        paths=managed_paths,
    )

    assert extension.kind == "extension"
    assert migrated.kind == "product"
    assert migrated.install_path == product
    assert (product / "module.py").read_text(encoding="utf-8") == "VALUE = 1\n"
    assert not (managed_paths.projects / "arthexis").exists()
    assert InstallState(managed_paths.state).get("arthexis") == migrated


def test_kind_migration_rejects_existing_product_target_without_force(
    make_project,
    managed_paths,
    monkeypatch,
):
    monkeypatch.setattr(transaction, "_converge_product_runtime", _fake_product_runtime)
    source = make_project("arthexis")
    transaction.install_local(
        InstallRequest(str(source), kind="extension"),
        paths=managed_paths,
    )
    product = managed_paths.products / "arthexis"
    transaction._copy_project(source, product)

    with pytest.raises(RuntimeError, match="New product destination already exists"):
        transaction.install_local(
            InstallRequest(str(source), kind="product"),
            paths=managed_paths,
        )


def test_forced_kind_migration_rejects_different_project_target(
    make_project,
    managed_paths,
    monkeypatch,
):
    monkeypatch.setattr(transaction, "_converge_product_runtime", _fake_product_runtime)
    source = make_project("arthexis")
    transaction.install_local(
        InstallRequest(str(source), kind="extension"),
        paths=managed_paths,
    )
    product = managed_paths.products / "arthexis"
    other = make_project("other")
    transaction._copy_project(other, product)

    with pytest.raises(RuntimeError, match="different project 'other'"):
        transaction.install_local(
            InstallRequest(str(source), kind="product", force=True),
            paths=managed_paths,
        )


def test_product_runtime_uses_uv_to_install_declared_dependencies(
    make_project,
    managed_paths,
    monkeypatch,
    tmp_path,
):
    project = make_project("arthexis", launcher=True)
    (project / "pyproject.toml").write_text(
        "[project]\n"
        "name = 'arthexis'\n"
        "dependencies = ['example-dependency>=1']\n"
        "\n[project.scripts]\n"
        "arthexis = 'arthexis:main'\n",
        encoding="utf-8",
    )
    uv = tmp_path / "uv"
    uv.write_text("", encoding="utf-8")
    calls = []

    monkeypatch.setattr("gway.recipe.uv.ensure_uv", lambda **kwargs: uv)

    def run(command, *, cwd, check):
        calls.append((tuple(command), Path(cwd), check))
        if command[1:] == ["venv", ".venv"]:
            python = _product_python(cwd)
            python.parent.mkdir(parents=True)
            python.write_text("", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(transaction.subprocess, "run", run)

    transaction._converge_product_runtime(project, managed_paths)

    python = _product_python(project)
    assert calls == [
        ((str(uv), "venv", ".venv"), project, True),
        (
            (
                str(uv),
                "pip",
                "install",
                "--python",
                str(python),
                "example-dependency>=1",
            ),
            project,
            True,
        ),
        (
            (str(uv), "pip", "check", "--python", str(python)),
            project,
            True,
        ),
    ]


def test_product_virtualenv_does_not_count_as_source_drift(make_project):
    project = make_project("arthexis")
    before = fingerprint(project)

    generated = project / ".venv" / "lib" / "python" / "site-packages"
    generated.mkdir(parents=True)
    (generated / "celery.py").write_text("VALUE = 1\n", encoding="utf-8")

    assert fingerprint(project) == before


def test_product_script_runs_with_product_owned_dependency(
    make_project,
    managed_paths,
    monkeypatch,
):
    from gway.install.ops import install

    source = make_project("arthexis", launcher=True)
    package = source / "arthexis" / "__init__.py"
    package.write_text(
        "import product_dependency\n"
        "def main():\n"
        "    return product_dependency.VALUE\n",
        encoding="utf-8",
    )

    def provision(project, selected):
        _fake_product_runtime(project, selected)
        python = _product_python(project)
        probe = subprocess.run(
            [
                str(python),
                "-c",
                "import site; print(site.getsitepackages()[0])",
            ],
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        )
        site_packages = Path(probe.stdout.strip())
        (site_packages / "product_dependency.py").write_text(
            "VALUE = 42\n",
            encoding="utf-8",
        )

    monkeypatch.setattr(transaction, "_converge_product_runtime", provision)

    installed = install(source, paths=managed_paths)

    assert invoke_target(installed.install_path, "arthexis:main") == 42
    assert _product_python(installed.install_path).is_file()
    assert fingerprint(installed.install_path) == installed.fingerprint


def test_reinstall_repairs_missing_product_runtime(
    make_project,
    managed_paths,
    monkeypatch,
):
    from gway.install.ops import install

    calls = []

    def provision(project, selected):
        calls.append(Path(project))
        _fake_product_runtime(project, selected)

    monkeypatch.setattr(transaction, "_converge_product_runtime", provision)

    source = make_project("arthexis", launcher=True)
    first = install(source, paths=managed_paths)
    runtime = first.install_path / ".venv"
    assert _product_python(first.install_path).is_file()

    transaction._remove_path(runtime)
    assert not _product_python(first.install_path).exists()

    second = install(source, paths=managed_paths)

    assert len(calls) == 2
    assert second.install_path == first.install_path
    assert _product_python(second.install_path).is_file()
    assert fingerprint(second.install_path) == second.fingerprint
    assert InstallState(managed_paths.state).get("arthexis") == second


def test_no_upgrade_still_repairs_missing_product_runtime(
    make_project,
    managed_paths,
    monkeypatch,
):
    from gway.install.ops import install

    monkeypatch.setattr(transaction, "_converge_product_runtime", _fake_product_runtime)

    source = make_project("arthexis", launcher=True)
    first = install(source, paths=managed_paths)
    transaction._remove_path(first.install_path / ".venv")

    repaired = install(source, paths=managed_paths, upgrade=False)

    assert _product_python(repaired.install_path).is_file()
    assert fingerprint(repaired.install_path) == repaired.fingerprint


def test_product_runtime_is_provisioned_at_final_destination(
    make_project,
    managed_paths,
    monkeypatch,
):
    from gway.install.ops import install

    observed = []

    def provision(project, selected):
        observed.append(Path(project))
        _fake_product_runtime(project, selected)

    monkeypatch.setattr(transaction, "_converge_product_runtime", provision)

    source = make_project("arthexis", launcher=True)
    installed = install(source, paths=managed_paths)

    assert observed == [installed.install_path]
    assert ".stage-" not in str(observed[0])


def test_product_runtime_convergence_reinstalls_declared_dependencies(
    make_project,
    managed_paths,
    monkeypatch,
    tmp_path,
):
    project = make_project("arthexis", launcher=True)
    _fake_product_runtime(project, managed_paths)
    uv = tmp_path / "uv"
    uv.write_text("", encoding="utf-8")
    observed = []

    monkeypatch.setattr("gway.recipe.uv.ensure_uv", lambda **kwargs: uv)

    def run(command, **kwargs):
        observed.append((tuple(command), kwargs))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(transaction.subprocess, "run", run)

    transaction._converge_product_runtime(project, managed_paths)

    assert observed[0][0] == (
        str(uv),
        "pip",
        "install",
        "--python",
        str(_product_python(project)),
        "example-dependency>=1",
    )
    assert observed[1][0] == (
        str(uv),
        "pip",
        "check",
        "--python",
        str(_product_python(project)),
    )

def test_failed_product_provisioning_restores_previous_install(
    make_project,
    managed_paths,
    monkeypatch,
):
    from gway.install.ops import install

    monkeypatch.setattr(transaction, "_converge_product_runtime", _fake_product_runtime)
    monkeypatch.setattr(transaction, "_converge_product_runtime", lambda *args: True)

    source = make_project("arthexis", launcher=True)
    first = install(source, paths=managed_paths)
    original = (first.install_path / "arthexis" / "__init__.py").read_text(
        encoding="utf-8"
    )

    (source / "arthexis" / "__init__.py").write_text(
        "def main():\n    return 99\n",
        encoding="utf-8",
    )

    def fail(project, selected):
        raise RuntimeError("dependency install failed")

    monkeypatch.setattr(transaction, "_converge_product_runtime", fail)

    with pytest.raises(RuntimeError, match="dependency install failed"):
        install(source, paths=managed_paths)

    assert (first.install_path / "arthexis" / "__init__.py").read_text(
        encoding="utf-8"
    ) == original
    assert InstallState(managed_paths.state).get("arthexis") == first


def test_product_dependencies_accept_minimal_project_metadata(make_project):
    project = make_project("arthexis")
    assert transaction._product_dependencies(project) == ()


def test_product_dependencies_read_pep621_runtime_requirements(make_project):
    project = make_project("arthexis")
    (project / "pyproject.toml").write_text(
        "[project]\n"
        "name = 'arthexis'\n"
        "dependencies = ['celery==5.5.3', 'Django==5.2.12']\n",
        encoding="utf-8",
    )

    assert transaction._product_dependencies(project) == (
        "celery==5.5.3",
        "Django==5.2.12",
    )
