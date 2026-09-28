from types import SimpleNamespace

from gway.githubops import Controller


class FakeClient:
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


def test_ruleset_and_branch_protection_reads_map_to_admin_endpoints():
    client = FakeClient(
        responses=[
            {"id": 7, "name": "Protect main"},
            {"required_status_checks": {"strict": True}},
        ],
        pages=[[{"id": 1}], [{"id": 2}]],
    )
    target = Controller(None, client=client)

    assert target.rulesets("arthexis/gway") == [{"id": 1}, {"id": 2}]
    assert target.ruleset("arthexis/gway", 7)["name"] == "Protect main"
    assert target.branch_protection("arthexis/gway", "release/test") == {
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
    client = FakeClient(
        responses=[{"permission": "maintain", "user": {"login": "alice"}}],
        pages=[[{"login": "alice", "permissions": {"maintain": True}}]],
    )
    target = Controller(None, client=client)

    assert target.collaborators(
        "arthexis/gway",
        affiliation="direct",
        permission="push",
    )[0]["login"] == "alice"
    assert target.collaborator_permission("arthexis/gway", "alice")[
        "permission"
    ] == "maintain"

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
    client = FakeClient(
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

    assert target.webhooks("arthexis/gway") == [{"id": 3, "active": True}]
    assert target.webhook("arthexis/gway", 4)["active"] is True
    assert target.actions_permissions("arthexis/gway") == {
        "enabled_repositories": "all"
    }
    assert target.actions_workflow_permissions("arthexis/gway")[
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


def complete_ruleset_policy():
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
            {
                "type": "deletion",
            },
            {
                "type": "non_fast_forward",
            },
        ],
    }


def test_ruleset_mutations_require_complete_explicit_policy():
    client = FakeClient(
        responses=[
            {"id": 11, "name": "Protect main"},
            {"id": 11, "name": "Protect main"},
            None,
        ]
    )
    target = Controller(None, client=client)
    policy = complete_ruleset_policy()

    created = target.create_ruleset("arthexis/gway", policy)
    updated = target.update_ruleset("arthexis/gway", 11, policy)
    deleted = target.delete_ruleset("arthexis/gway", 11)

    assert created["id"] == 11
    assert updated["id"] == 11
    assert deleted == {
        "repository": "arthexis/gway",
        "ruleset": 11,
        "deleted": True,
    }
    assert client.calls == [
        ("POST", "/repos/arthexis/gway/rulesets", None),
        ("PUT", "/repos/arthexis/gway/rulesets/11", None),
        ("DELETE", "/repos/arthexis/gway/rulesets/11", None),
    ]
    assert client.payloads == [policy, policy, None]


def test_ruleset_policy_rejects_partial_or_implicit_patch_shape():
    target = Controller(None, client=FakeClient())

    try:
        target.create_ruleset(
            "arthexis/gway",
            {
                "name": "Protect main",
                "target": "branch",
                "enforcement": "active",
            },
        )
    except ValueError as error:
        assert "missing required fields" in str(error)
    else:
        raise AssertionError("partial ruleset policy unexpectedly accepted")


def test_ruleset_mutations_respect_no_mutate_before_network_access():
    client = FakeClient()
    target = Controller(None, client=client)
    policy = complete_ruleset_policy()

    for call in (
        lambda: target.create_ruleset("arthexis/gway", policy, mutate=False),
        lambda: target.update_ruleset("arthexis/gway", 11, policy, mutate=False),
        lambda: target.delete_ruleset("arthexis/gway", 11, mutate=False),
    ):
        try:
            call()
        except PermissionError as error:
            assert "ruleset mutation is disabled" in str(error)
        else:
            raise AssertionError("ruleset mutation unexpectedly allowed")

    assert client.calls == []


def complete_branch_protection_policy():
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


def test_branch_protection_mutations_require_complete_explicit_policy():
    client = FakeClient(
        responses=[
            {"url": "https://api.github.test/protection"},
            None,
        ]
    )
    target = Controller(None, client=client)
    policy = complete_branch_protection_policy()

    updated = target.update_branch_protection(
        "arthexis/gway",
        "release/test",
        policy,
    )
    deleted = target.delete_branch_protection(
        "arthexis/gway",
        "release/test",
    )

    assert updated["url"] == "https://api.github.test/protection"
    assert deleted == {
        "repository": "arthexis/gway",
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
    assert client.payloads == [policy, None]


def test_branch_protection_rejects_partial_policy():
    target = Controller(None, client=FakeClient())

    try:
        target.update_branch_protection(
            "arthexis/gway",
            "main",
            {
                "required_status_checks": None,
                "enforce_admins": True,
            },
        )
    except ValueError as error:
        assert "missing required fields" in str(error)
    else:
        raise AssertionError("partial branch protection unexpectedly accepted")


def test_branch_protection_mutations_respect_no_mutate_before_network_access():
    client = FakeClient()
    target = Controller(None, client=client)
    policy = complete_branch_protection_policy()

    for call in (
        lambda: target.update_branch_protection(
            "arthexis/gway",
            "main",
            policy,
            mutate=False,
        ),
        lambda: target.delete_branch_protection(
            "arthexis/gway",
            "main",
            mutate=False,
        ),
    ):
        try:
            call()
        except PermissionError as error:
            assert "branch protection mutation is disabled" in str(error)
        else:
            raise AssertionError("branch protection mutation unexpectedly allowed")

    assert client.calls == []
