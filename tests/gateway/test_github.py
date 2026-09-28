import pytest

from gway.githubops import ADMIN_OPERATIONS, WRITE_OPERATIONS

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


ADMIN_READ_OPERATIONS = {
    "rulesets",
    "ruleset",
    "branch_protection",
    "collaborators",
    "collaborator_permission",
    "webhooks",
    "webhook",
    "actions_permissions",
    "actions_workflow_permissions",
}

ADMIN_WRITE_OPERATIONS = {
    "create_ruleset",
    "update_ruleset",
    "delete_ruleset",
    "update_branch_protection",
    "delete_branch_protection",
    "set_actions_permissions",
    "set_actions_workflow_permissions",
}


@pytest.mark.parametrize(
    ("operation_name", "access"),
    [
        *((f"github.{name}", "read") for name in sorted(ADMIN_READ_OPERATIONS)),
        *((f"github.{name}", "write") for name in sorted(ADMIN_WRITE_OPERATIONS)),
    ],
)
def test_github_admin_operation_matrix(gateway, operation_name, access):
    operation = gateway.ops.resolve(operation_name)
    assert operation is not None
    topics = set(operation.__gway_metadata__["topics"])

    assert {"github", "source", "admin", access} <= topics
    assert len({"read", "write"} & topics) == 1
    assert operation.mutates is (access == "write")


def test_github_admin_sets_match_registry_classification(gateway):
    registered = {
        record.name.removeprefix("github.")
        for record in gateway.ops.records()
        if record.name.startswith("github.")
        and "admin" in set(record.callable.__gway_metadata__["topics"])
    }

    expected = ADMIN_READ_OPERATIONS | ADMIN_WRITE_OPERATIONS

    assert registered == expected
    assert set(ADMIN_OPERATIONS) == expected
    assert set(ADMIN_OPERATIONS) & set(WRITE_OPERATIONS) == ADMIN_WRITE_OPERATIONS


def test_actions_policy_boolean_parameters_bind_from_command_text(gateway):
    from types import SimpleNamespace

    calls = []

    class Client:
        def request(self, method, path, *, params=None, json=None, headers=None):
            calls.append((method, path, json))
            return SimpleNamespace(data=None)

    gateway._github_controller._client = Client()

    gateway.execute(
        "github set actions permissions arthexis/gway "
        "--enabled true --allowed-actions selected --sha-pinning-required false"
    )
    gateway.execute(
        "github set actions workflow permissions arthexis/gway "
        "--default-workflow-permissions read "
        "--can-approve-pull-request-reviews false"
    )

    assert calls == [
        (
            "PUT",
            "/repos/arthexis/gway/actions/permissions",
            {
                "enabled": True,
                "allowed_actions": "selected",
                "sha_pinning_required": False,
            },
        ),
        (
            "PUT",
            "/repos/arthexis/gway/actions/permissions/workflow",
            {
                "default_workflow_permissions": "read",
                "can_approve_pull_request_reviews": False,
            },
        ),
    ]


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
            assert record.name.removeprefix("github.") in ADMIN_OPERATIONS
