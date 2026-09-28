from types import SimpleNamespace

from gway.githubops import Controller


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, path, *, params=None, json=None, headers=None):
        self.calls.append((method, path, params))
        return SimpleNamespace(data=self.responses.pop(0))

    def pages(self, path, *, params=None):
        self.calls.append(("PAGES", path, params))
        for data in self.responses:
            yield SimpleNamespace(data=data)


def test_collaboration_reads_map_to_github_resources():
    client = FakeClient([
        {"number": 7},
        {"number": 8},
        [{"id": 1}],
        [{"id": 2}],
    ])
    target = Controller(None, client=client)

    assert target.pull("arthexis/gway", 7)["number"] == 7
    assert target.issue("arthexis/gway", 8)["number"] == 8
    assert target.reviews("arthexis/gway", 7) == [{"id": 1}]
    client.responses = [[{"id": 2}]]
    assert target.comments("arthexis/gway", 7) == [{"id": 2}]


def test_ci_reads_unwrap_github_collection_envelopes():
    client = FakeClient([
        {"workflows": [{"id": 1}]},
        {"workflow_runs": [{"id": 2}]},
        {"jobs": [{"id": 3}]},
        {"check_runs": [{"id": 4}]},
    ])
    target = Controller(None, client=client)

    assert target.workflows("arthexis/gway") == [{"id": 1}]
    assert target.runs("arthexis/gway") == [{"id": 2}]
    assert target.jobs("arthexis/gway", 10) == [{"id": 3}]
    assert target.checks("arthexis/gway", "abc") == [{"id": 4}]


def test_configuration_reads_expose_secret_metadata_only():
    client = FakeClient([
        {"variables": [{"name": "MODE", "value": "prod"}]},
        {"secrets": [{"name": "TOKEN", "created_at": "now"}]},
        {"name": "TOKEN", "created_at": "now"},
    ])
    target = Controller(None, client=client)

    assert target.variables("arthexis/gway")[0]["value"] == "prod"
    secrets = target.secrets("arthexis/gway")
    secret = target.secret("arthexis/gway", "TOKEN")

    assert secrets == [{"name": "TOKEN", "created_at": "now"}]
    assert secret == {"name": "TOKEN", "created_at": "now"}
    assert "value" not in secrets[0]
    assert "value" not in secret
