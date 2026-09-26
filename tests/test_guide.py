import pytest

from gway import Gateway
from gway.config import project_guidance


def test_project_guidance_validates_explicit_rules():
    rules = project_guidance(
        {
            "tool": {
                "gway": {
                    "guide": [
                        {
                            "tasks": ["check logs", "inspect production logs"],
                            "command": "log read --all",
                            "reason": "Use the maintained log reader.",
                        }
                    ]
                }
            }
        },
        source="demo",
    )

    assert rules == (
        {
            "tasks": ("check logs", "inspect production logs"),
            "command": "log read --all",
            "reason": "Use the maintained log reader.",
            "source": "demo",
        },
    )


@pytest.mark.parametrize(
    "entry, message",
    [
        ({"tasks": [], "command": "status", "reason": "x"}, "non-empty tasks"),
        ({"tasks": ["status"], "reason": "x"}, "non-empty command"),
        ({"tasks": ["status"], "command": "status"}, "non-empty reason"),
        (
            {"tasks": ["status"], "command": "status", "reason": "x", "extra": True},
            "Unknown guide fields",
        ),
    ],
)
def test_project_guidance_rejects_invalid_rules(entry, message):
    with pytest.raises(ValueError, match=message):
        project_guidance({"tool": {"gway": {"guide": [entry]}}})


def test_guide_returns_ranked_explicit_project_recommendations(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "demo"

[[tool.gway.guide]]
tasks = ["check production logs", "inspect logs"]
command = "log read --all"
reason = "Use the maintained log reader."

[[tool.gway.guide]]
tasks = ["check production"]
command = "status"
reason = "Inspect the project status."
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    gateway = Gateway()

    result = gateway("guide check production logs")

    assert result["task"] == "check production logs"
    assert result["recommendations"][0] == {
        "kind": "gway",
        "command": "log read --all",
        "reason": "Use the maintained log reader.",
        "source": "demo",
        "matched_task": "check production logs",
    }
    assert result["external"] == []


def test_guide_is_read_only_and_empty_without_matching_explicit_guidance(
    tmp_path,
    monkeypatch,
):
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "demo"

[[tool.gway.guide]]
tasks = ["check logs"]
command = "log read --all"
reason = "Use logs."
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    gateway = Gateway()

    result = gateway.execute("guide deploy database", mutate=False)

    assert result == {
        "task": "deploy database",
        "recommendations": [],
        "external": [],
    }
    assert gateway.guide.mutates is False
