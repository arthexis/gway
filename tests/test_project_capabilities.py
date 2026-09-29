import pytest

from gway import Gateway
from gway.config import project_scopes, project_watch


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
