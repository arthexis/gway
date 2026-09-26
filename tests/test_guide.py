import pytest

from gway import Gateway
from gway.config import project_guide_documents, project_guidance


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
            "use": "gway",
            "command": "log read --all",
            "capability": None,
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
        (
            {
                "tasks": ["review pull request"],
                "use": "external",
                "command": "status",
                "capability": "source-control",
                "reason": "Use source control.",
            },
            "external guide declaration cannot define command",
        ),
        (
            {
                "tasks": ["review pull request"],
                "use": "external",
                "reason": "Use source control.",
            },
            "requires a non-empty capability",
        ),
        (
            {
                "tasks": ["status"],
                "command": "status",
                "capability": "source-control",
                "reason": "x",
            },
            "cannot define capability",
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


def test_guide_returns_explicit_external_capability(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "demo"

[[tool.gway.guide]]
tasks = ["review pull request", "check ci"]
use = "external"
capability = "source-control"
reason = "The repository is the canonical development surface."
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    gateway = Gateway()

    result = gateway("guide review pull request")

    assert result["external"] == [
        {
            "capability": "source-control",
            "reason": "The repository is the canonical development surface.",
            "source": "demo",
            "matched_task": "review pull request",
        }
    ]


def test_external_guide_honors_role_filtering(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "demo"

[tool.gway.variables]
role = "watchtower"

[[tool.gway.guide]]
tasks = ["edit deployment source"]
use = "external"
capability = "source-control"
reason = "Modify source in the repository."
roles = ["watchtower"]

[[tool.gway.guide]]
tasks = ["edit deployment source"]
use = "external"
capability = "file-editor"
reason = "Terminal-only local edit."
roles = ["terminal"]
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    gateway = Gateway()

    result = gateway("guide edit deployment source")

    assert [item["capability"] for item in result["external"]] == [
        "source-control"
    ]


def test_external_guidance_is_independent_of_gway_authorization(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "demo"

[[tool.gway.guide]]
tasks = ["check ci"]
use = "external"
capability = "source-control"
reason = "Inspect CI in source control."
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    gateway = Gateway()

    with gateway.authorized(operations={"guide"}):
        result = gateway("guide check ci")

    assert result["external"][0]["capability"] == "source-control"


def test_project_role_specific_guidance_implies_role_and_source(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "demo"

[tool.gway.variables]
role = "watchtower"

[[tool.gway.roles.watchtower.guide]]
tasks = ["diagnose this node"]
command = "node watchtower diagnose"
reason = "Use the Watchtower diagnostic family."
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    gateway = Gateway()

    result = gateway("guide diagnose this node")

    assert result["role"] == "watchtower"
    assert result["recommendations"][0] == {
        "kind": "gway",
        "command": "node watchtower diagnose",
        "reason": "Use the Watchtower diagnostic family.",
        "source": "demo:watchtower",
        "matched_task": "diagnose this node",
        "roles": ["watchtower"],
    }


def test_role_specific_project_guidance_is_hidden_for_other_roles(
    tmp_path,
    monkeypatch,
):
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "demo"

[tool.gway.variables]
role = "control"

[[tool.gway.roles.watchtower.guide]]
tasks = ["diagnose this node"]
command = "node watchtower diagnose"
reason = "Watchtower diagnostic."
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    gateway = Gateway()

    result = gateway("guide diagnose this node")

    assert all(
        item.get("command") != "node watchtower diagnose"
        for item in result["recommendations"]
    )


def test_role_specific_project_guidance_rejects_explicit_roles():
    with pytest.raises(ValueError, match="cannot define roles"):
        project_guidance(
            {
                "tool": {
                    "gway": {
                        "roles": {
                            "watchtower": {
                                "guide": [
                                    {
                                        "tasks": ["diagnose"],
                                        "command": "node watchtower diagnose",
                                        "reason": "x",
                                        "roles": ["terminal"],
                                    }
                                ]
                            }
                        }
                    }
                }
            },
            source="demo",
        )


def test_role_specific_project_guidance_supports_external_capability(
    tmp_path,
    monkeypatch,
):
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "demo"

[tool.gway.variables]
role = "watchtower"

[[tool.gway.roles.watchtower.guide]]
tasks = ["review deployment source"]
use = "external"
capability = "source-control"
reason = "Review the canonical repository."
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    gateway = Gateway()

    result = gateway("guide review deployment source")

    assert result["external"][0] == {
        "capability": "source-control",
        "reason": "Review the canonical repository.",
        "source": "demo:watchtower",
        "matched_task": "review deployment source",
        "roles": ["watchtower"],
    }


def test_guide_uses_only_explicitly_selected_project_documents(tmp_path, monkeypatch):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "OPERATIONS.md").write_text(
        """
# Deployment recovery

To diagnose a failed deployment, inspect the recovery journal and verify the
deployed source revision before attempting another rollout.
""".lstrip(),
        encoding="utf-8",
    )
    (tmp_path / "docs" / "PRIVATE.md").write_text(
        "# Secret recovery\nUse the hidden emergency procedure.\n",
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "demo"

[tool.gway]
guide_documents = ["docs/OPERATIONS.md"]
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    gateway = Gateway()

    result = gateway("guide diagnose failed deployment")

    docs = [
        item for item in result["recommendations"]
        if item.get("kind") == "documentation"
    ]
    assert docs
    assert docs[0]["source"] == "docs/OPERATIONS.md"
    assert docs[0]["section"] == "Deployment recovery"
    assert "recovery journal" in docs[0]["reason"]
    assert all(item["source"] != "docs/PRIVATE.md" for item in docs)


def test_document_fallback_is_ranked_after_operational_guidance(tmp_path, monkeypatch):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "OPS.md").write_text(
        "# Inspect service\nInspect service health with the normal service command.\n",
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "demo"

[tool.gway]
guide_documents = ["docs/OPS.md"]
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    gateway = Gateway()

    def inspect_service():
        """Inspect service health."""

    gateway.wrap("inspect.service", inspect_service)
    result = gateway("guide inspect service health")

    operation_index = next(
        index for index, item in enumerate(result["recommendations"])
        if item.get("operation") == "inspect.service"
    )
    document_index = next(
        index for index, item in enumerate(result["recommendations"])
        if item.get("kind") == "documentation"
    )
    assert operation_index < document_index


@pytest.mark.parametrize(
    "selected",
    [
        ["../outside.md"],
        ["/tmp/outside.md"],
    ],
)
def test_project_guide_documents_rejects_paths_outside_project(tmp_path, selected):
    with pytest.raises(ValueError, match="stay within the project"):
        project_guide_documents(
            {"tool": {"gway": {"guide_documents": selected}}},
            tmp_path,
        )


def test_project_guide_documents_rejects_oversized_file(tmp_path):
    path = tmp_path / "OPS.md"
    path.write_text("x" * 65537, encoding="utf-8")

    with pytest.raises(ValueError, match="exceeds 65536 bytes"):
        project_guide_documents(
            {"tool": {"gway": {"guide_documents": ["OPS.md"]}}},
            tmp_path,
        )


def test_project_guide_documents_rejects_unselected_format(tmp_path):
    path = tmp_path / "OPS.py"
    path.write_text("print('not documentation')\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Markdown or text"):
        project_guide_documents(
            {"tool": {"gway": {"guide_documents": ["OPS.py"]}}},
            tmp_path,
        )


def test_guide_uses_richer_docstring_after_operation_and_recipe_fallbacks(
    tmp_path,
    monkeypatch,
):
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "demo"
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("gway.sampler.recipes", lambda: ())
    gateway = Gateway()

    def inspect_service():
        """Inspect service.

        Use this operation to investigate transient worker failures and queue
        starvation when the ordinary status summary is insufficient.
        """

    gateway.wrap("inspect.service", inspect_service)

    result = gateway("guide investigate worker queue starvation")

    inferred = next(
        item for item in result["recommendations"]
        if item.get("operation") == "inspect.service"
    )
    assert inferred["source"] == "docstring"
    assert "queue starvation" in inferred["reason"]


def test_docstring_fallback_is_authorization_aware(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "demo"
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("gway.sampler.recipes", lambda: ())
    gateway = Gateway()

    def audit_secret():
        """Investigate secret rotation failures and leaked credential state."""

    gateway.wrap("audit.secret", audit_secret)

    with gateway.authorized(operations={"guide"}):
        result = gateway("guide investigate secret rotation failures")

    assert all(
        item.get("operation") != "audit.secret"
        for item in result["recommendations"]
    )


def test_guide_role_lookup_does_not_require_env_authority(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "demo"

[tool.gway.variables]
role = "watchtower"

[[tool.gway.roles.watchtower.guide]]
tasks = ["diagnose this node"]
command = "node watchtower diagnose"
reason = "Use role-specific diagnostics."
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    gateway = Gateway()

    with gateway.authorized(operations={"guide"}):
        result = gateway("guide diagnose this node")

    assert result["role"] == "watchtower"
    assert result["recommendations"][0]["command"] == "node watchtower diagnose"
