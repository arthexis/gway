from types import SimpleNamespace

from gway.githubops import Controller


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, path, *, params=None, json=None, headers=None):
        self.calls.append((method, path, params))
        response = self.responses.pop(0)
        if isinstance(response, tuple):
            data, status, response_headers = response
        else:
            data, status, response_headers = response, 200, {}
        return SimpleNamespace(
            data=data,
            status=status,
            headers=response_headers,
        )


def test_runs_support_workflow_branch_and_status_filters():
    client = FakeClient([{"workflow_runs": [{"id": 7}]}])
    target = Controller(None, client=client)

    assert target.runs(
        "arthexis/gway",
        workflow="ci.yml",
        branch="main",
        status="failure",
    ) == [{"id": 7}]
    assert client.calls == [
        (
            "GET",
            "/repos/arthexis/gway/actions/workflows/ci.yml/runs",
            {"per_page": 100, "branch": "main", "status": "failure"},
        )
    ]


def test_jobs_and_checks_unwrap_github_collection_envelopes():
    client = FakeClient(
        [
            {"jobs": [{"id": 11, "conclusion": "failure"}]},
            {"check_runs": [{"id": 22, "conclusion": "failure"}]},
        ]
    )
    target = Controller(None, client=client)

    assert target.jobs("arthexis/gway", 7)[0]["id"] == 11
    assert target.checks("arthexis/gway", "abc")[0]["id"] == 22


def test_runs_follow_enveloped_pagination():
    class PagingClient:
        def __init__(self):
            self.calls = []

        def request(self, method, path, *, params=None, json=None, headers=None):
            self.calls.append((method, path, params))
            if len(self.calls) == 1:
                return SimpleNamespace(
                    data={"workflow_runs": [{"id": 1}]},
                    next_url="https://api.github.com/repos/arthexis/gway/actions/runs?page=2",
                )
            return SimpleNamespace(
                data={"workflow_runs": [{"id": 2}]},
                next_url=None,
            )

    client = PagingClient()
    target = Controller(None, client=client)

    assert target.runs("arthexis/gway") == [{"id": 1}, {"id": 2}]
    assert client.calls == [
        (
            "GET",
            "/repos/arthexis/gway/actions/runs",
            {"per_page": 100},
        ),
        (
            "GET",
            "https://api.github.com/repos/arthexis/gway/actions/runs?page=2",
            None,
        ),
    ]


def test_job_logs_preserve_diagnostic_content_and_type():
    client = FakeClient(
        [
            (
                "step one\nfailed\n",
                200,
                {"content-type": "text/plain"},
            )
        ]
    )
    target = Controller(None, client=client)

    assert target.job_logs("arthexis/gway", 11) == {
        "status": 200,
        "content": "step one\nfailed\n",
        "content_type": "text/plain",
    }


def test_ci_diagnostic_operations_are_non_mutating_source_reads(gateway):
    names = {
        "github.runs",
        "github.run",
        "github.jobs",
        "github.job",
        "github.checks",
        "github.check",
        "github.job_logs",
    }
    for name in names:
        operation = gateway.ops.resolve(name)
        assert operation is not None
        assert operation.mutates is False
        assert {"github", "source", "read"} <= set(
            operation.__gway_metadata__["topics"]
        )
