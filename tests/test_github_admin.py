from types import SimpleNamespace

import pytest

from gway.githubops import Controller


REPOSITORY = "arthexis/gway"


class RecordingClient:
    def __init__(self, responses=(), pages=()):
        self.responses = list(responses)
        self.page_data = list(pages)
        self.calls = []
        self.payloads = []

    def request(self, method, path, *, params=None, json=None, headers=None):
        self.calls.append((method, path, params))
        self.payloads.append(json)
        return SimpleNamespace(data=self.responses.pop(0))

    def pages(self, path, *, params=None):
        self.calls.append(("PAGES", path, params))
        for data in self.page_data:
            yield SimpleNamespace(data=data)


@pytest.fixture
def ruleset_policy():
    return {
        "name": "Protect main",
        "target": "branch",
        "enforcement": "active",
        "bypass_actors": [],
        "conditions": {
            "ref_name": {
                "include": ["refs/heads/main"],
                "exclude": [],
            }
        },
        "rules": [
            {"type": "deletion"},
            {"type": "non_fast_forward"},
        ],
    }


@pytest.fixture
def branch_protection_policy():
    return {
        "required_status_checks": {
            "strict": True,
            "contexts": ["python / Quality"],
        },
        "enforce_admins": True,
        "required_pull_request_reviews": {
            "dismiss_stale_reviews": True,
            "require_code_owner_reviews": False,
            "required_approving_review_count": 1,
            "require_last_push_approval": True,
        },
        "restrictions": None,
        "required_linear_history": True,
        "allow_force_pushes": False,
        "allow_deletions": False,
        "block_creations": False,
        "required_conversation_resolution": True,
        "lock_branch": False,
        "allow_fork_syncing": False,
    }


def test_ruleset_and_branch_protection_reads_map_to_admin_endpoints():
    client = RecordingClient(
        responses=[
            {"id": 7, "name": "Protect main"},
            {"required_status_checks": {"strict": True}},
        ],
        pages=[[{"id": 1}], [{"id": 2}]],
    )
    target = Controller(None, client=client)

    assert target.rulesets(REPOSITORY) == [{"id": 1}, {"id": 2}]
    assert target.ruleset(REPOSITORY, 7)["name"] == "Protect main"
    assert target.branch_protection(REPOSITORY, "release/test") == {
        "required_status_checks": {"strict": True}
    }
    assert client.calls == [
        ("PAGES", "/repos/arthexis/gway/rulesets", {"per_page": 100}),
        ("GET", "/repos/arthexis/gway/rulesets/7", None),
        (
            "GET",
            "/repos/arthexis/gway/branches/release%2Ftest/protection",
            None,
        ),
    ]


def test_collaborator_admin_reads_expose_permissions_only_from_github():
    client = RecordingClient(
        responses=[{"permission": "maintain", "user": {"login": "alice"}}],
        pages=[[{"login": "alice", "permissions": {"maintain": True}}]],
    )
    target = Controller(None, client=client)

    assert target.collaborators(
        REPOSITORY,
        affiliation="direct",
        permission="push",
    )[0]["login"] == "alice"
    assert target.collaborator_permission(REPOSITORY, "alice")["permission"] == "maintain"
    assert client.calls == [
        (
            "PAGES",
            "/repos/arthexis/gway/collaborators",
            {"per_page": 100, "affiliation": "direct", "permission": "push"},
        ),
        (
            "GET",
            "/repos/arthexis/gway/collaborators/alice/permission",
            None,
        ),
    ]


def test_webhook_and_actions_policy_reads_map_to_admin_endpoints():
    client = RecordingClient(
        responses=[
            {"id": 4, "active": True},
            {"enabled_repositories": "all"},
            {
                "default_workflow_permissions": "read",
                "can_approve_pull_request_reviews": False,
            },
        ],
        pages=[[{"id": 3, "active": True}]],
    )
    target = Controller(None, client=client)

    assert target.webhooks(REPOSITORY) == [{"id": 3, "active": True}]
    assert target.webhook(REPOSITORY, 4)["active"] is True
    assert target.actions_permissions(REPOSITORY) == {"enabled_repositories": "all"}
    assert target.actions_workflow_permissions(REPOSITORY)[
        "default_workflow_permissions"
    ] == "read"
    assert client.calls == [
        ("PAGES", "/repos/arthexis/gway/hooks", {"per_page": 100}),
        ("GET", "/repos/arthexis/gway/hooks/4", None),
        ("GET", "/repos/arthexis/gway/actions/permissions", None),
        (
            "GET",
            "/repos/arthexis/gway/actions/permissions/workflow",
            None,
        ),
    ]


def test_ruleset_mutations_send_complete_explicit_policy(ruleset_policy):
    client = RecordingClient(
        responses=[
            {"id": 11, "name": "Protect main"},
            {"id": 11, "name": "Protect main"},
            None,
        ]
    )
    target = Controller(None, client=client)

    assert target.create_ruleset(REPOSITORY, ruleset_policy)["id"] == 11
    assert target.update_ruleset(REPOSITORY, 11, ruleset_policy)["id"] == 11
    assert target.delete_ruleset(REPOSITORY, 11) == {
        "repository": REPOSITORY,
        "ruleset": 11,
        "deleted": True,
    }
    assert client.calls == [
        ("POST", "/repos/arthexis/gway/rulesets", None),
        ("PUT", "/repos/arthexis/gway/rulesets/11", None),
        ("DELETE", "/repos/arthexis/gway/rulesets/11", None),
    ]
    assert client.payloads == [ruleset_policy, ruleset_policy, None]


def test_ruleset_policy_rejects_partial_shape():
    target = Controller(None, client=RecordingClient())

    with pytest.raises(ValueError, match="missing required fields"):
        target.create_ruleset(
            REPOSITORY,
            {
                "name": "Protect main",
                "target": "branch",
                "enforcement": "active",
            },
        )


def test_branch_protection_mutations_send_complete_explicit_policy(
    branch_protection_policy,
):
    client = RecordingClient(
        responses=[
            {"url": "https://api.github.test/protection"},
            None,
        ]
    )
    target = Controller(None, client=client)

    assert target.update_branch_protection(
        REPOSITORY,
        "release/test",
        branch_protection_policy,
    )["url"] == "https://api.github.test/protection"
    assert target.delete_branch_protection(REPOSITORY, "release/test") == {
        "repository": REPOSITORY,
        "branch": "release/test",
        "deleted": True,
    }
    assert client.calls == [
        (
            "PUT",
            "/repos/arthexis/gway/branches/release%2Ftest/protection",
            None,
        ),
        (
            "DELETE",
            "/repos/arthexis/gway/branches/release%2Ftest/protection",
            None,
        ),
    ]
    assert client.payloads == [branch_protection_policy, None]


def test_branch_protection_rejects_partial_policy():
    target = Controller(None, client=RecordingClient())

    with pytest.raises(ValueError, match="missing required fields"):
        target.update_branch_protection(
            REPOSITORY,
            "main",
            {
                "required_status_checks": None,
                "enforce_admins": True,
            },
        )


def test_actions_policy_mutations_send_complete_explicit_payloads():
    client = RecordingClient(responses=[None, None])
    target = Controller(None, client=client)

    assert target.set_actions_permissions(
        REPOSITORY,
        True,
        "selected",
        True,
    ) == {
        "repository": REPOSITORY,
        "enabled": True,
        "allowed_actions": "selected",
        "sha_pinning_required": True,
        "updated": True,
    }
    assert target.set_actions_workflow_permissions(
        REPOSITORY,
        "read",
        False,
    ) == {
        "repository": REPOSITORY,
        "default_workflow_permissions": "read",
        "can_approve_pull_request_reviews": False,
        "updated": True,
    }
    assert client.calls == [
        ("PUT", "/repos/arthexis/gway/actions/permissions", None),
        (
            "PUT",
            "/repos/arthexis/gway/actions/permissions/workflow",
            None,
        ),
    ]
    assert client.payloads == [
        {
            "enabled": True,
            "allowed_actions": "selected",
            "sha_pinning_required": True,
        },
        {
            "default_workflow_permissions": "read",
            "can_approve_pull_request_reviews": False,
        },
    ]


@pytest.mark.parametrize(
    ("operation", "args", "message"),
    [
        (
            "set_actions_permissions",
            (REPOSITORY, True, "invalid", False),
            "allowed_actions",
        ),
        (
            "set_actions_workflow_permissions",
            (REPOSITORY, "admin", False),
            "read or write",
        ),
    ],
)
def test_actions_policy_mutations_validate_security_fields(operation, args, message):
    target = Controller(None, client=RecordingClient())

    with pytest.raises(ValueError, match=message):
        getattr(target, operation)(*args)


@pytest.mark.parametrize(
    ("operation", "arguments"),
    [
        ("delete_ruleset", (REPOSITORY, 11)),
        ("delete_branch_protection", (REPOSITORY, "main")),
        ("set_actions_permissions", (REPOSITORY, True, "all", False)),
        (
            "set_actions_workflow_permissions",
            (REPOSITORY, "read", False),
        ),
    ],
)
def test_admin_mutations_respect_no_mutate_before_network_access(operation, arguments):
    client = RecordingClient()
    target = Controller(None, client=client)

    with pytest.raises(PermissionError, match="mutation is disabled"):
        getattr(target, operation)(*arguments, mutate=False)

    assert client.calls == []


def test_complete_policy_mutations_respect_no_mutate_before_network_access(
    ruleset_policy,
    branch_protection_policy,
):
    client = RecordingClient()
    target = Controller(None, client=client)

    calls = (
        lambda: target.create_ruleset(REPOSITORY, ruleset_policy, mutate=False),
        lambda: target.update_ruleset(REPOSITORY, 11, ruleset_policy, mutate=False),
        lambda: target.update_branch_protection(
            REPOSITORY,
            "main",
            branch_protection_policy,
            mutate=False,
        ),
    )
    for call in calls:
        with pytest.raises(PermissionError, match="mutation is disabled"):
            call()

    assert client.calls == []
