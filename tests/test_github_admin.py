from types import SimpleNamespace

from gway.githubops import Controller


class FakeClient:
    def __init__(self, responses=(), pages=()):
        self.responses = list(responses)
        self.page_data = list(pages)
        self.calls = []

    def request(self, method, path, *, params=None, json=None, headers=None):
        self.calls.append((method, path, params))
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
