import pytest

from gway import Gateway
from gway.config import project_survey


def _document():
    return {
        "tool": {
            "gway": {
                "survey": [
                    {
                        "section": "demo",
                        "command": ["demo", "status"],
                    }
                ],
            }
        }
    }


def test_project_survey_metadata_is_normalized():
    survey = project_survey(_document(), source="demo")

    assert survey == (
        {
            "section": "demo",
            "command": ("demo", "status"),
            "source": "demo",
        },
    )


def test_local_project_publishes_survey_without_creating_security_state(
    tmp_path,
    monkeypatch,
):
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "demo"

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

    assert not gateway.security_path.exists()
    assert gateway._survey_contributors == (
        {
            "section": "demo",
            "command": ("demo", "status"),
            "source": "demo",
        },
    )


def test_retired_project_scope_declaration_has_no_authorization_effect(
    tmp_path,
    monkeypatch,
):
    project_file = tmp_path / "pyproject.toml"
    project_file.write_text(
        """
[project]
name = "demo"

# Retained here deliberately: legacy project scope declarations are inert.
[tool.gway.scopes.demo-read]
operations = ["demo.status"]
environment = []
semantic_terms = ["demo", "read"]

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

    assert project_file.is_file()
    assert not gateway.security_path.exists()
    assert vars(gateway).get("_published_scopes") is None
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

[[tool.gway.survey]]
section = "demo"
command = ["demo", "status"]
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.chdir(project)

    gateway = Gateway()

    assert gateway.security_path == cache / "security" / "state.sqlite"
    assert not gateway.security_path.exists()