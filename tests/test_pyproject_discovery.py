from types import SimpleNamespace

import pytest

from gway.config import _valid_installation, find_project_file
from gway.install.ops import _local_intent
from gway.install.source import project_name
from gway.project import project_scripts


def test_project_name_uses_pyproject_without_gway_toml(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\n',
        encoding="utf-8",
    )

    assert project_name(tmp_path) == "demo"


def test_project_name_rejects_gway_toml_only_project(tmp_path):
    (tmp_path / "gway.toml").write_text(
        '[project]\nname = "legacy"\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="requires pyproject.toml"):
        project_name(tmp_path)


def test_find_project_file_prefers_pyproject(tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "demo"\n', encoding="utf-8")
    (tmp_path / "gway.toml").write_text(
        '[project]\nname = "legacy"\n',
        encoding="utf-8",
    )

    assert find_project_file(tmp_path) == pyproject


def test_local_intent_recognizes_pyproject_project(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\n',
        encoding="utf-8",
    )

    assert _local_intent(str(tmp_path)) is True


def test_managed_installation_accepts_pyproject_without_gway_toml(tmp_path):
    projects = tmp_path / "projects"
    installed = projects / "demo"
    installed.mkdir(parents=True)
    (installed / "pyproject.toml").write_text(
        '[project]\nname = "demo"\n',
        encoding="utf-8",
    )
    record = SimpleNamespace(name="demo", install_path=installed)
    paths = SimpleNamespace(projects=projects)

    assert _valid_installation(record, paths) is True


def test_project_scripts_reads_standard_python_entrypoints(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\n[project.scripts]\nhello = "demo:main"\n',
        encoding="utf-8",
    )

    assert project_scripts(tmp_path) == {"hello": "demo:main"}


def test_standard_project_scripts_ignore_gway_toml(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\n[project.scripts]\nhello = "demo:new_main"\n',
        encoding="utf-8",
    )
    (tmp_path / "gway.toml").write_text(
        '[project]\nname = "demo"\n[install.scripts]\nlegacy = "demo:legacy_main"\n',
        encoding="utf-8",
    )

    assert project_scripts(tmp_path) == {"hello": "demo:new_main"}


def test_gateway_bootstrap_exposes_project_script_as_operation(tmp_path, monkeypatch):
    package = tmp_path / "demo.py"
    package.write_text(
        'def main(name="world"):\n    return f"hello {name}"\n',
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\n[project.scripts]\nhello = "demo:main"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    from gway.gateway import Gateway

    runtime = Gateway()

    assert runtime("hello Ada") == "hello Ada"
    assert runtime("demo hello Ada") == "hello Ada"


def test_gateway_bootstrap_does_not_import_project_script_dependencies(
    tmp_path,
    monkeypatch,
):
    (tmp_path / "demo.py").write_text(
        "import dependency_not_installed_in_gway\n"
        "def main():\n"
        "    return 0\n",
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\n[project.scripts]\nhello = "demo:main"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    from gway.gateway import Gateway

    runtime = Gateway()

    assert runtime.ops.resolve("hello") is not None
    with pytest.raises(ModuleNotFoundError, match="dependency_not_installed_in_gway"):
        runtime("hello")


def test_pyproject_semantic_variables_are_available_to_sigils(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\n[tool.gway.variables]\nregion = "local"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    from gway.gateway import Gateway

    runtime = Gateway()

    assert runtime.resolve("[region]") == "local"


def test_environment_overrides_pyproject_semantic_variables(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\n[tool.gway.variables]\nregion = "local"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("REGION", "production")
    monkeypatch.chdir(tmp_path)

    from gway.gateway import Gateway

    runtime = Gateway()

    assert runtime.resolve("[region]") == "production"


def test_pyproject_bootstrap_registers_ordered_physical_bindings(
    tmp_path, monkeypatch
):
    secret = tmp_path / "token"
    secret.write_text("file-value\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\n'
        '[[tool.gway.bindings]]\n'
        'topics = ["service", "vendor"]\n'
        'subject = "token"\n'
        'sources = [{type = "file", value = "' + str(secret) + '"}, '
        '{type = "env", value = "VENDOR_TOKEN"}]\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("VENDOR_TOKEN", "environment-value")
    monkeypatch.chdir(tmp_path)

    from gway.gateway import Gateway

    runtime = Gateway()

    with runtime.topics("service", "vendor"):
        assert runtime.resolve("[token]") == "file-value"


def test_pyproject_binding_topics_are_order_insensitive(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\n'
        '[[tool.gway.bindings]]\n'
        'topics = ["godaddy", "dns"]\n'
        'subject = "api_key"\n'
        'sources = [{type = "env", value = "GODADDY_API_KEY"}]\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("GODADDY_API_KEY", "bound")
    monkeypatch.chdir(tmp_path)

    from gway.gateway import Gateway

    runtime = Gateway()

    with runtime.topics("dns", "godaddy"):
        assert runtime.resolve("[api_key]") == "bound"


def test_pyproject_binding_declarations_compose_additively(tmp_path, monkeypatch):
    secret = tmp_path / "fallback"
    secret.write_text("fallback\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\n'
        '[[tool.gway.bindings]]\n'
        'topics = ["service", "vendor"]\n'
        'subject = "token"\n'
        'sources = [{type = "env", value = "MISSING_VENDOR_TOKEN"}]\n'
        '[[tool.gway.bindings]]\n'
        'topics = ["vendor", "service"]\n'
        'subject = "token"\n'
        'sources = [{type = "file", value = "' + str(secret) + '"}]\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    from gway.gateway import Gateway

    runtime = Gateway()

    with runtime.topics("service", "vendor"):
        assert runtime.resolve("[token]") == "fallback"


def test_pyproject_binding_replace_discards_prior_sources(tmp_path, monkeypatch):
    secret = tmp_path / "replacement"
    secret.write_text("replacement\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\n'
        '[[tool.gway.bindings]]\n'
        'topics = ["service", "vendor"]\n'
        'subject = "token"\n'
        'sources = [{type = "env", value = "VENDOR_TOKEN"}]\n'
        '[[tool.gway.bindings]]\n'
        'topics = ["service", "vendor"]\n'
        'subject = "token"\n'
        'replace = true\n'
        'sources = [{type = "file", value = "' + str(secret) + '"}]\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("VENDOR_TOKEN", "old")
    monkeypatch.chdir(tmp_path)

    from gway.gateway import Gateway

    runtime = Gateway()

    with runtime.topics("service", "vendor"):
        assert runtime.resolve("[token]") == "replacement"


@pytest.mark.parametrize(
    "source, message",
    [
        ('{type = "unknown", value = "x"}', "unknown binding source type"),
        ('{type = "env"}', "binding source requires value"),
    ],
)
def test_pyproject_binding_rejects_invalid_sources(
    tmp_path, monkeypatch, source, message
):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\n'
        '[[tool.gway.bindings]]\n'
        'topics = ["service"]\n'
        'subject = "token"\n'
        f"sources = [{source}]\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    from gway.gateway import Gateway

    with pytest.raises(ValueError, match=message):
        Gateway()


def test_pyproject_secret_binding_uses_secrets_backend(tmp_path, monkeypatch):
    root = tmp_path / "secrets"
    target = root / "service" / "vendor" / "token"
    target.parent.mkdir(parents=True)
    target.write_text("from-secret-backend\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\n'
        '[[tool.gway.bindings]]\n'
        'topics = ["service", "vendor"]\n'
        'subject = "token"\n'
        'sources = [{type = "secret", value = "service/vendor/token"}]\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("GWAY_SECRETS_DIR", str(root))
    monkeypatch.chdir(tmp_path)

    from gway.gateway import Gateway

    runtime = Gateway()

    with runtime.topics("vendor", "service"):
        assert runtime.resolve("[token]") == "from-secret-backend"


def test_project_binding_can_replace_provider_defaults(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\n'
        '[[tool.gway.bindings]]\n'
        'topics = ["dns", "godaddy"]\n'
        'subject = "api_key"\n'
        'replace = true\n'
        'sources = [{type = "env", value = "PROJECT_GODADDY_KEY", sensitive = true}]\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("PROJECT_GODADDY_KEY", "project-key")
    monkeypatch.setenv("GODADDY_API_KEY", "provider-default")
    monkeypatch.chdir(tmp_path)

    from gway.gateway import Gateway

    runtime = Gateway()

    with runtime.topics("dns", "godaddy"):
        assert runtime.resolve("[api_key]") == "project-key"
