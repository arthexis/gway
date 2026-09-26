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
            "roles": (),
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
        (
            {"tasks": [1], "command": "status", "reason": "x"},
            "non-empty strings",
        ),
        (
            {
                "tasks": ["status"],
                "command": "status",
                "reason": "x",
                "roles": [False],
            },
            "guide roles must be non-empty strings",
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


def test_guide_role_specific_rule_outranks_generic_rule(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "demo"

[tool.gway.variables]
role = "watchtower"

[[tool.gway.guide]]
tasks = ["diagnose node"]
command = "status"
reason = "Generic diagnostic."

[[tool.gway.guide]]
tasks = ["diagnose node"]
roles = ["watchtower"]
command = "node diagnose"
reason = "Use the Watchtower-specific diagnostic."
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    gateway = Gateway()

    result = gateway("guide diagnose node")

    assert result["role"] == "watchtower"
    assert result["recommendations"][0]["command"] == "node diagnose"
    assert result["recommendations"][0]["roles"] == ["watchtower"]
    assert result["recommendations"][1]["command"] == "status"


def test_guide_excludes_rules_for_other_roles(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "demo"

[tool.gway.variables]
role = "control"

[[tool.gway.guide]]
tasks = ["diagnose node"]
roles = ["watchtower"]
command = "node diagnose"
reason = "Watchtower-only diagnostic."
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    gateway = Gateway()

    result = gateway("guide diagnose node")

    assert result["role"] == "control"
    assert result["recommendations"] == []


def test_guide_result_does_not_publish_metadata_into_context(tmp_path, monkeypatch):
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
    gateway.context.update(
        {
            "task": "preserve-task",
            "recommendations": "preserve-recommendations",
            "external": "preserve-external",
        }
    )

    result = gateway("guide check logs")

    assert result["task"] == "check logs"
    assert gateway.context["task"] == "preserve-task"
    assert gateway.context["recommendations"] == "preserve-recommendations"
    assert gateway.context["external"] == "preserve-external"


def test_guide_falls_back_to_live_registered_operation_metadata(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "demo"
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    gateway = Gateway()

    def inspect_service():
        """Inspect service health."""

    gateway.wrap("inspect.service", inspect_service)

    result = gateway("guide inspect service health")

    inferred = next(
        item for item in result["recommendations"]
        if item.get("operation") == "inspect.service"
    )
    assert inferred["command"] == "inspect service"
    assert inferred["reason"] == "Inspect service health."
    assert inferred["source"] == "runtime"
    assert inferred["mutates"] is True


def test_explicit_guide_precedes_and_deduplicates_live_operation(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "demo"

[[tool.gway.guide]]
tasks = ["inspect service health"]
command = "inspect service"
reason = "Use the project's preferred service inspection path."
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    gateway = Gateway()

    def inspect_service():
        """Inspect service health."""

    gateway.wrap("inspect.service", inspect_service)

    result = gateway("guide inspect service health")

    matching = [
        item for item in result["recommendations"]
        if item["command"] == "inspect service"
    ]
    assert matching == [
        {
            "kind": "gway",
            "command": "inspect service",
            "reason": "Use the project's preferred service inspection path.",
            "source": "demo",
            "matched_task": "inspect service health",
        }
    ]


def test_guide_hides_unauthorized_live_operations(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "demo"
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    gateway = Gateway()

    def inspect_service():
        """Inspect service health."""

    def delete_secret():
        """Delete secret data."""

    gateway.wrap("inspect.service", inspect_service)
    gateway.wrap("delete.secret", delete_secret)

    with gateway.authorized(operations={"guide", "inspect.service"}):
        result = gateway("guide delete secret data")

    assert all(
        item.get("operation") != "delete.secret"
        for item in result["recommendations"]
    )


def test_guide_falls_back_to_maintained_sampler_recipe(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "demo"
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "gway.sampler.recipes",
        lambda: ("web/expose/http", "remote/accept"),
    )
    gateway = Gateway()

    result = gateway("guide expose web http")

    recipe = next(
        item for item in result["recommendations"]
        if item.get("recipe") == "web/expose/http"
    )
    assert recipe == {
        "kind": "recipe",
        "command": "recipe web/expose/http",
        "reason": "Maintained sampler recipe: web/expose/http.",
        "source": "sampler",
        "recipe": "web/expose/http",
        "mutates": True,
    }


def test_guide_hides_sampler_recipes_without_recipe_authority(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "demo"
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "gway.sampler.recipes",
        lambda: ("web/expose/http",),
    )
    gateway = Gateway()

    with gateway.authorized(operations={"guide"}):
        result = gateway("guide expose web http")

    assert all(item.get("kind") != "recipe" for item in result["recommendations"])


def test_guide_allows_sampler_recipes_with_recipe_authority(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "demo"
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "gway.sampler.recipes",
        lambda: ("web/expose/http",),
    )
    gateway = Gateway()

    with gateway.authorized(operations={"guide", "recipe"}):
        result = gateway("guide expose web http")

    assert any(
        item.get("recipe") == "web/expose/http"
        for item in result["recommendations"]
    )
