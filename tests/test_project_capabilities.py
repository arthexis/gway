import pytest

from gway import Gateway
from gway.config import project_scopes, project_watch
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
                "watch": [
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
    watch = project_watch(_document(), source="demo")

    assert scopes == {
        "demo-read": {
            "operations": frozenset({"demo.status"}),
            "environment": frozenset(),
            "source": "demo",
        }
    }
    assert watch == (
        {
            "section": "demo",
            "command": ("demo", "status"),
            "source": "demo",
        },
    )


def test_local_project_publishes_scopes_and_watch(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "demo"

[tool.gway.scopes.demo-read]
operations = ["demo.status"]
environment = []

[[tool.gway.watch]]
section = "demo"
command = ["demo", "status"]
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    gateway = Gateway()

    assert gateway._published_scopes["demo-read"]["operations"] == frozenset(
        {"demo.status"}
    )
    assert not gateway.security_path.exists()

    scopes = gateway._token_controller.scopes()
    assert {scope.name for scope in scopes} >= {"demo-read"}

    registered = ScopeRegistry(gateway.security_path).require("demo-read")
    assert registered.operations == frozenset({"demo.status"})
    assert gateway._watch_contributors == (
        {
            "section": "demo",
            "command": ("demo", "status"),
            "source": "demo",
        },
    )


def test_project_watch_rejects_ambiguous_command_string():
    document = _document()
    document["tool"]["gway"]["watch"][0]["command"] = "demo status"

    with pytest.raises(ValueError, match="string array"):
        project_watch(document)


def test_published_scope_refuses_to_claim_user_managed_scope(tmp_path):
    registry = ScopeRegistry(tmp_path / "security.sqlite")
    registry.replace(
        "demo-read",
        operations={"manual.status"},
        environment=(),
    )

    with pytest.raises(ValueError, match="user-managed"):
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
    assert scope.owner is None
    assert scope.operations == frozenset({"manual.status"})



def test_published_scope_claims_matching_legacy_unowned_scope(tmp_path):
    registry = ScopeRegistry(tmp_path / "security.sqlite")
    registry.replace(
        "demo-read",
        operations={"demo.status"},
        environment=(),
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


def test_published_scope_refuses_to_claim_nonmatching_legacy_unowned_scope(tmp_path):
    registry = ScopeRegistry(tmp_path / "security.sqlite")
    registry.replace(
        "demo-read",
        operations={"demo.status", "manual.extra"},
        environment=(),
    )

    with pytest.raises(ValueError, match="user-managed"):
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
    assert scope.owner is None
    assert scope.operations == frozenset({"demo.status", "manual.extra"})

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
