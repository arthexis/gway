from types import SimpleNamespace

from gway.githubops import Controller


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, path, *, params=None, json=None, headers=None):
        self.calls.append((method, path, params))
        return SimpleNamespace(data=self.responses.pop(0))


def test_variables_preserve_api_visible_values():
    client = FakeClient(
        [
            {
                "variables": [
                    {
                        "name": "DEPLOY_ENV",
                        "value": "production",
                        "updated_at": "2026-09-28T00:00:00Z",
                    }
                ]
            },
            {"name": "DEPLOY_ENV", "value": "production"},
        ]
    )
    target = Controller(None, client=client)

    assert target.variables("arthexis/gway")[0]["value"] == "production"
    assert target.variable("arthexis/gway", "DEPLOY_ENV")["value"] == "production"


def test_secrets_return_metadata_only():
    metadata = {
        "name": "OPENAI_API_KEY",
        "created_at": "2026-09-01T00:00:00Z",
        "updated_at": "2026-09-28T00:00:00Z",
    }
    client = FakeClient([{"secrets": [metadata]}, metadata])
    target = Controller(None, client=client)

    listed = target.secrets("arthexis/gway")
    single = target.secret("arthexis/gway", "OPENAI_API_KEY")

    assert listed == [metadata]
    assert single == metadata
    assert "value" not in listed[0]
    assert "value" not in single


def test_configuration_reads_use_actions_endpoints():
    client = FakeClient([{"variables": []}, {"secrets": []}])
    target = Controller(None, client=client)

    target.variables("arthexis/gway")
    target.secrets("arthexis/gway")

    assert client.calls == [
        (
            "GET",
            "/repos/arthexis/gway/actions/variables",
            {"per_page": 100},
        ),
        (
            "GET",
            "/repos/arthexis/gway/actions/secrets",
            {"per_page": 100},
        ),
    ]


def test_configuration_reads_are_non_mutating_source_reads(gateway):
    for name in {
        "github.variables",
        "github.variable",
        "github.secrets",
        "github.secret",
    }:
        operation = gateway.ops.resolve(name)
        assert operation is not None
        assert operation.mutates is False
        assert {"github", "source", "read"} <= set(
            operation.__gway_metadata__["topics"]
        )
