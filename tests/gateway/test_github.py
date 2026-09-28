import pytest

def test_github_operations_are_registered_as_source_read(gateway):
    expected = {
        "github.repository",
        "github.status",
        "github.branches",
        "github.branch",
        "github.commits",
        "github.commit",
        "github.file",
        "github.tree",
        "github.ref",
        "github.refs",
        "github.tags",
        "github.pulls",
        "github.pull",
        "github.reviews",
        "github.comments",
        "github.issues",
        "github.issue",
        "github.workflows",
        "github.workflow",
        "github.runs",
        "github.run",
        "github.jobs",
        "github.checks",
        "github.releases",
        "github.release",
        "github.variables",
        "github.variable",
        "github.secrets",
        "github.secret",
        "github.review_comments",
        "github.review_threads",
        "github.job",
        "github.check",
        "github.job_logs",
        "github.release_tag",
        "github.latest_release",
    }

    for name in expected:
        operation = gateway.ops.resolve(name)
        assert operation is not None
        assert operation.mutates is False
        topics = set(operation.__gway_metadata__["topics"])
        assert {"github", "source", "read"} <= topics


def test_github_admin_reads_are_separate_from_mutation(gateway):
    expected = {
        "github.rulesets",
        "github.ruleset",
        "github.branch_protection",
        "github.collaborators",
        "github.collaborator_permission",
        "github.webhooks",
        "github.webhook",
        "github.actions_permissions",
        "github.actions_workflow_permissions",
    }

    for name in expected:
        operation = gateway.ops.resolve(name)
        assert operation is not None
        assert operation.mutates is False
        topics = set(operation.__gway_metadata__["topics"])
        assert {"github", "source", "read", "admin"} <= topics
        assert "write" not in topics


def test_github_reads_respect_authorization(gateway):
    from gway.authorization import AuthorizationError

    with gateway.authorized(operations={"github.status"}):
        operation = gateway.ops.resolve("github.status")
        assert operation is not None

    with gateway.authorized(operations={"env"}):
        with pytest.raises(AuthorizationError):
            gateway.execute("github status arthexis/gway", mutate=False)


def test_github_reads_support_no_mutate(gateway):
    operation = gateway.ops.resolve("github.status")

    assert operation.mutates is False
    assert gateway.execute("help github status", mutate=False)


def test_every_github_operation_has_exactly_one_access_topic(gateway):
    for record in gateway.ops.records():
        if not record.name.startswith("github."):
            continue
        topics = set(record.callable.__gway_metadata__["topics"])
        assert {"github", "source"} <= topics
        assert len({"read", "write"} & topics) == 1
        assert record.callable.mutates is ("write" in topics)
        if "admin" in topics:
            assert record.name.removeprefix("github.") in {
                "rulesets",
                "ruleset",
                "create_ruleset",
                "update_ruleset",
                "delete_ruleset",
                "branch_protection",
                "collaborators",
                "collaborator_permission",
                "webhooks",
                "webhook",
                "actions_permissions",
                "actions_workflow_permissions",
            }
