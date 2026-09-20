"""End-to-end acceptance tests for the rebuilt Gway architecture."""

from gway import Gateway
from gway.ingestion.base import find_ingested


def test_pyproject_only_project_exposes_scripts_package_main_and_variables(
    tmp_path,
    monkeypatch,
):
    (tmp_path / "demo.py").write_text(
        "def greet(name='world'):\n"
        "    return f'hello {name}'\n",
        encoding="utf-8",
    )
    package = tmp_path / "worker"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "__main__.py").write_text(
        "import sys\n"
        "ARGS = sys.argv[1:]\n",
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text(
        "[project]\n"
        "name = 'demo'\n"
        "[project.scripts]\n"
        "hello = 'demo:greet'\n"
        "[tool.gway.variables]\n"
        "region = 'local'\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    runtime = Gateway()

    assert runtime("hello Ada") == "hello Ada"
    assert runtime("demo hello Grace") == "hello Grace"
    assert runtime("worker alpha beta")["ARGS"] == ["alpha", "beta"]
    assert runtime.resolve("[region]") == "local"


def test_managed_project_expands_standard_script_only_when_used(
    tmp_path,
    monkeypatch,
):
    data = tmp_path / "data"
    cache = tmp_path / "cache"
    bin_dir = tmp_path / "bin"
    monkeypatch.setenv("GWAY_DATA_DIR", str(data))
    monkeypatch.setenv("GWAY_CACHE_DIR", str(cache))
    monkeypatch.setenv("GWAY_BIN_DIR", str(bin_dir))

    source = tmp_path / "source"
    source.mkdir()
    (source / "pyproject.toml").write_text(
        "[project]\n"
        "name = 'tool'\n"
        "[project.scripts]\n"
        "tool = 'tool:main'\n",
        encoding="utf-8",
    )
    package = source / "tool"
    package.mkdir()
    (package / "__init__.py").write_text(
        "def main():\n"
        "    return 0\n",
        encoding="utf-8",
    )

    installed = Gateway()(f"install {source}")

    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.chdir(outside)

    runtime = Gateway()
    record = find_ingested(runtime, ("tool",))

    assert runtime._installed["tool"] == installed
    assert record is not None
    assert record.expanded is False

    assert runtime("tool tool") == 0

    assert record.expanded is True
    assert runtime.ops.resolve("tool.tool") is not None


def test_generic_operation_service_preserves_invocation_and_policy(monkeypatch):
    runtime = Gateway()
    captured = {}

    def worker(*, queue="default"):
        return queue

    runtime.wrap("worker", worker)

    class Backend:
        @staticmethod
        def install_units(project, services, **kwargs):
            captured["project"] = project
            captured["service"] = tuple(services)[0]
            return ["installed"]

    monkeypatch.setattr("gway.install.service.get", lambda name: Backend)

    result = runtime(
        "service install --backend process --name urgent "
        "--restart always --attempts 4 --restart-sec 0.5 "
        "-- worker --queue urgent"
    )

    service = captured["service"]
    assert result == ["installed"]
    assert service.name == "urgent"
    assert service.restart == "always"
    assert service.attempts == 4
    assert service.restart_sec == 0.5
    assert service.launchable.command[-2:] == ("--queue", "urgent")


def test_recipe_can_be_installed_as_service_without_declaration(
    tmp_path,
    monkeypatch,
):
    runtime = Gateway()
    recipe = tmp_path / "nightly.rx"
    recipe.write_text("", encoding="utf-8")
    captured = {}

    class Backend:
        @staticmethod
        def install_units(project, services, **kwargs):
            captured["service"] = tuple(services)[0]
            return ["installed"]

    monkeypatch.setattr("gway.install.service.get", lambda name: Backend)

    result = runtime(
        f"service install --backend process -- {recipe}"
    )

    service = captured["service"]
    assert result == ["installed"]
    assert service.launchable.kind == "recipe"
    assert service.launchable.target == recipe.resolve()
    assert service.launchable.command == (
        "{python}",
        "-m",
        "gway",
        str(recipe.resolve()),
    )


def test_sous_chef_foreground_and_service_use_same_launchable(monkeypatch):
    runtime = Gateway()
    launchable = runtime.launchables["sous.chef"]
    preset = runtime._service_presets[("gway", "sous-chef")]
    captured = {}

    class Backend:
        @staticmethod
        def install_units(project, services, **kwargs):
            captured["service"] = tuple(services)[0]
            return ["installed"]

    monkeypatch.setattr("gway.install.service.get", lambda name: Backend)

    result = runtime("service install --backend process sous chef")

    assert result == ["installed"]
    assert preset.launchable is launchable
    assert captured["service"].launchable.name == launchable.name
    assert captured["service"].launchable.command == launchable.command


def test_environment_overrides_pyproject_semantic_variable(
    tmp_path,
    monkeypatch,
):
    (tmp_path / "pyproject.toml").write_text(
        "[project]\n"
        "name = 'demo'\n"
        "[tool.gway.variables]\n"
        "region = 'local'\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("REGION", "production")
    monkeypatch.chdir(tmp_path)

    runtime = Gateway()

    assert runtime.resolve("[region]") == "production"


def _install_project(runtime, root, name, *, script=None, package_main=None):
    root.mkdir()
    metadata = ["[project]\n", f"name = {name!r}\n"]
    if script is not None:
        command, target = script
        metadata.extend(
            [
                "[project.scripts]\n",
                f"{command} = {target!r}\n",
            ]
        )
    (root / "pyproject.toml").write_text(
        "".join(metadata),
        encoding="utf-8",
    )

    if script is not None:
        _, target = script
        module_name = target.split(":", 1)[0]
        module = root / f"{module_name}.py"
        module.write_text(
            "def main(value='ok'):\n"
            "    return value\n",
            encoding="utf-8",
        )

    if package_main is not None:
        package = root / package_main
        package.mkdir()
        (package / "__init__.py").write_text("", encoding="utf-8")
        (package / "__main__.py").write_text(
            "import sys\n"
            "ARGS = sys.argv[1:]\n",
            encoding="utf-8",
        )

    return runtime(f"install {root}")


def test_unique_installed_script_resolves_bare_before_project_expansion(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("GWAY_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GWAY_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("GWAY_BIN_DIR", str(tmp_path / "bin"))

    _install_project(
        Gateway(),
        tmp_path / "source",
        "acme",
        script=("hello", "entry:main"),
    )

    outside = tmp_path / "outside-script"
    outside.mkdir()
    monkeypatch.chdir(outside)
    runtime = Gateway()
    record = find_ingested(runtime, ("acme",))

    assert record is not None
    assert ("hello",) in record.paths
    assert record.expanded is False

    assert runtime("hello Ada") == "Ada"

    assert record.expanded is True
    assert runtime.ops.resolve("acme.hello") is not None


def test_unique_installed_package_main_resolves_bare_lazily(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("GWAY_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GWAY_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("GWAY_BIN_DIR", str(tmp_path / "bin"))

    _install_project(
        Gateway(),
        tmp_path / "source",
        "acme",
        package_main="worker",
    )

    outside = tmp_path / "outside-main"
    outside.mkdir()
    monkeypatch.chdir(outside)
    runtime = Gateway()
    record = find_ingested(runtime, ("acme",))

    assert record is not None
    assert ("worker",) in record.paths
    assert record.expanded is False

    result = runtime("worker alpha beta")

    assert result["ARGS"] == ["alpha", "beta"]
    assert record.expanded is True
    assert runtime.ops.resolve("acme.worker") is not None


def test_duplicate_installed_script_names_require_project_qualification(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("GWAY_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GWAY_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("GWAY_BIN_DIR", str(tmp_path / "bin"))

    installer = Gateway()
    _install_project(
        installer,
        tmp_path / "one",
        "one",
        script=("hello", "entry:main"),
    )
    _install_project(
        installer,
        tmp_path / "two",
        "two",
        script=("hello", "entry:main"),
    )

    outside = tmp_path / "outside-duplicate-script"
    outside.mkdir()
    monkeypatch.chdir(outside)
    runtime = Gateway()

    assert find_ingested(runtime, ("hello",)) is None

    import pytest

    with pytest.raises(LookupError):
        runtime("hello")

    assert runtime("one hello first") == "first"

    with pytest.raises(LookupError):
        runtime("hello")

    assert runtime("two hello second") == "second"


def test_duplicate_installed_package_mains_require_project_qualification(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("GWAY_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GWAY_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("GWAY_BIN_DIR", str(tmp_path / "bin"))

    installer = Gateway()
    _install_project(
        installer,
        tmp_path / "one",
        "one",
        package_main="worker",
    )
    _install_project(
        installer,
        tmp_path / "two",
        "two",
        package_main="worker",
    )

    outside = tmp_path / "outside-duplicate-main"
    outside.mkdir()
    monkeypatch.chdir(outside)
    runtime = Gateway()

    assert find_ingested(runtime, ("worker",)) is None

    import pytest

    with pytest.raises(LookupError):
        runtime("worker")

    assert runtime("one worker first")["ARGS"] == ["first"]

    with pytest.raises(LookupError):
        runtime("worker")

    assert runtime("two worker second")["ARGS"] == ["second"]
