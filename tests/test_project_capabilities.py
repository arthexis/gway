import pytest

from gway import Gateway
from gway.config import project_scopes, project_survey
from gway.security.defaults import converge_scope_registry
from gway.security.scopes import ScopeRegistry


def _document():
    return {
        "tool": {
            "gway": {
                "scopes": {
                    "demo-read": {
                        "operations": ["demo.status"],
                        "environment": [],
                    }
                },
                "survey": [
                    {
                        "section": "demo",
                        "command": ["demo", "status"],
                    }
                ],
            }
        }
    }


def test_project_capability_metadata_is_normalized():
    scopes = project_scopes(_document(), source="demo")
    survey = project_survey(_document(), source="demo")

    assert scopes == {
        "demo-read": {
            "operations": frozenset({"demo.status"}),
            "environment": frozenset(),
            "source": "demo",
        }
    }
    assert survey == (
        {
            "section": "demo",
            "command": ("demo", "status"),
            "source": "demo",
        },
    )


def test_project_scope_semantic_terms_are_normalized():
    document = _document()
    document["tool"]["gway"]["scopes"]["demo-read"]["semantic_terms"] = [
        " Demo ",
        "READ",
        "demo",
    ]

    scopes = project_scopes(document, source="demo")

    assert scopes["demo-read"]["semantic_terms"] == frozenset({"demo", "read"})


@pytest.mark.parametrize("semantic_terms", ["demo,read", [], ["demo", " "]])
def test_project_scope_rejects_malformed_semantic_terms(semantic_terms):
    document = _document()
    document["tool"]["gway"]["scopes"]["demo-read"]["semantic_terms"] = semantic_terms

    with pytest.raises(ValueError, match="semantic_terms"):
        project_scopes(document)


def test_semantic_project_scope_is_validated_before_publication(gateway):
    from gway.config import _publish_project_capabilities

    safe = gateway.wrap("demo.read", lambda: None)
    safe.mutates = False
    safe.__gway_mutates__ = False
    document = _document()
    document["tool"]["gway"]["scopes"]["demo-read"]["operations"] = ["demo.read"]
    document["tool"]["gway"]["scopes"]["demo-read"]["semantic_terms"] = [
        "demo",
        "read",
    ]

    _publish_project_capabilities(gateway, document, source="demo")

    assert gateway._published_scopes["demo-read"]["semantic_terms"] == frozenset(
        {"demo", "read"}
    )


def test_unsafe_semantic_project_scope_fails_before_publication_or_persistence(
    gateway, tmp_path
):
    from gway.config import _publish_project_capabilities

    gateway.security_path = tmp_path / "security.sqlite"
    unsafe = gateway.wrap("demo.create", lambda: None)
    unsafe.mutates = True
    unsafe.__gway_mutates__ = True
    document = _document()
    document["tool"]["gway"]["scopes"]["demo-read"]["operations"] = ["demo.create"]
    document["tool"]["gway"]["scopes"]["demo-read"]["semantic_terms"] = [
        "demo",
        "read",
    ]

    with pytest.raises(ValueError, match="mutating: demo.create"):
        _publish_project_capabilities(gateway, document, source="demo")

    assert "demo-read" not in getattr(gateway, "_published_scopes", {})
    assert not gateway.security_path.exists()


def test_local_project_publishes_scopes_and_survey(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "demo"

[tool.gway.scopes.demo-read]
operations = ["demo.status"]
environment = []

[[tool.gway.survey]]
section = "demo"
command = ["demo", "status"]
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GWAY_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GWAY_CACHE_DIR", str(tmp_path / "cache"))

    gateway = Gateway()

    assert gateway._published_scopes["demo-read"]["operations"] == frozenset(
        {"demo.status"}
    )
    assert not gateway.security_path.exists()

    scopes = gateway._token_controller.scopes()
    assert {scope.name for scope in scopes} >= {"demo-read"}

    registered = ScopeRegistry(gateway.security_path).require("demo-read")
    assert registered.operations == frozenset({"demo.status"})
    assert gateway._survey_contributors == (
        {
            "section": "demo",
            "command": ("demo", "status"),
            "source": "demo",
        },
    )


def test_project_survey_rejects_ambiguous_command_string():
    document = _document()
    document["tool"]["gway"]["survey"][0]["command"] = "demo status"

    with pytest.raises(ValueError, match="string array"):
        project_survey(document)


def test_published_scope_replaces_legacy_unowned_definition(tmp_path):
    registry = ScopeRegistry(tmp_path / "security.sqlite")
    registry.replace(
        "demo-read",
        operations={"legacy.status", "manual.extra"},
        environment={"LEGACY_ENV"},
    )

    converge_scope_registry(
        registry,
        {
            "demo-read": {
                "operations": frozenset({"demo.status"}),
                "environment": frozenset(),
                "source": "demo",
            }
        },
    )

    scope = registry.require("demo-read")
    assert scope.owner == "project:demo"
    assert scope.operations == frozenset({"demo.status"})
    assert scope.environment == frozenset()


def test_retired_product_scope_is_removed_without_touching_user_scope(tmp_path):
    registry = ScopeRegistry(tmp_path / "security.sqlite")
    registry.replace("manual-read", operations={"manual.status"}, environment=())
    converge_scope_registry(
        registry,
        {
            "demo-read": {
                "operations": frozenset({"demo.status"}),
                "environment": frozenset(),
                "source": "demo",
            }
        },
    )
    assert registry.require("demo-read").owner == "project:demo"

    converge_scope_registry(registry, {})

    with pytest.raises(LookupError, match="demo-read"):
        registry.require("demo-read")
    manual = registry.require("manual-read")
    assert manual.owner is None
    assert manual.operations == frozenset({"manual.status"})


def test_duplicate_publishers_cannot_share_scope_name(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    for root, project, operation in (
        (first, "first", "first.status"),
        (second, "second", "second.status"),
    ):
        (root / "pyproject.toml").write_text(
            f"""
[project]
name = "{project}"

[tool.gway.scopes.shared-read]
operations = ["{operation}"]
environment = []
""".lstrip(),
            encoding="utf-8",
        )

    from gway.config import _publish_project_capabilities
    from gway import toml

    gateway = Gateway()
    _publish_project_capabilities(
        gateway,
        toml.load(first / "pyproject.toml"),
        source="first",
    )
    with pytest.raises(ValueError, match="collision"):
        _publish_project_capabilities(
            gateway,
            toml.load(second / "pyproject.toml"),
            source="second",
        )


def test_gateway_help_bootstrap_does_not_require_writable_security_state(
    tmp_path,
    monkeypatch,
):
    project = tmp_path / "project"
    project.mkdir()
    cache = tmp_path / "system-cache"
    (project / "pyproject.toml").write_text(
        f"""
[project]
name = "demo"

[tool.gway.variables]
cache_dir = "{cache}"

[tool.gway.scopes.demo-read]
operations = ["demo.status"]
environment = []
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.chdir(project)

    gateway = Gateway()

    assert gateway.security_path == cache / "security" / "state.sqlite"
    assert not gateway.security_path.exists()
    assert gateway._published_scopes["demo-read"]["operations"] == frozenset(
        {"demo.status"}
    )


def test_scope_resolve_converges_on_first_use(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    cache = tmp_path / "cache"
    (project / "pyproject.toml").write_text(
        f"""
[project]
name = "demo"

[tool.gway.variables]
cache_dir = "{cache}"

[tool.gway.scopes.demo-read]
operations = ["demo.status"]
environment = []
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.chdir(project)

    gateway = Gateway()
    assert not gateway.security_path.exists()

    resolved = gateway._scope_controller.resolve("demo-read")

    assert resolved.operations == frozenset({"demo.status"})


def test_execute_authenticated_converges_published_scope_updates(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    cache = tmp_path / "cache"
    project_file = project / "pyproject.toml"
    project_file.write_text(
        f"""
[project]
name = "demo"

[tool.gway.variables]
cache_dir = "{cache}"

[tool.gway.scopes.demo-read]
operations = ["help"]
environment = []
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.chdir(project)

    gateway = Gateway()
    bearer = gateway._token_controller.create("demo-token", "demo-read")

    project_file.write_text(
        f"""
[project]
name = "demo"

[tool.gway.variables]
cache_dir = "{cache}"

[tool.gway.scopes.demo-read]
operations = ["version"]
environment = []
""".lstrip(),
        encoding="utf-8",
    )

    refreshed = Gateway()

    with pytest.raises(PermissionError):
        refreshed.execute_authenticated(bearer, "help")

    result = refreshed.execute_authenticated(bearer, "version")
    assert result is not None
