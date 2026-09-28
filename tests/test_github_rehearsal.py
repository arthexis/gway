from types import SimpleNamespace

from gway.githubops import Controller


class DiagnosticClient:
    def __init__(self):
        self.calls = []

    def request(self, method, path, *, params=None, json=None, headers=None):
        self.calls.append((method, path, params))
        if path.endswith("/pulls/1218"):
            data = {"number": 1218, "head": {"sha": "abc"}}
        elif path.endswith("/commits/abc/check-runs"):
            data = {"check_runs": [{"id": 22, "conclusion": "failure"}]}
        elif path.endswith("/actions/runs/7/jobs"):
            data = {"jobs": [{"id": 11, "conclusion": "failure"}]}
        elif path.endswith("/actions/jobs/11/logs"):
            return SimpleNamespace(
                data="Ruff lint failed\n",
                status=200,
                headers={"content-type": "text/plain"},
            )
        else:
            data = {"workflow_runs": [{"id": 7, "conclusion": "failure"}]}
        return SimpleNamespace(data=data, status=200, headers={})

    def graphql(self, query, variables=None):
        self.calls.append(("GRAPHQL", variables.copy()))
        return SimpleNamespace(
            data={
                "data": {
                    "repository": {
                        "pullRequest": {
                            "reviewThreads": {
                                "nodes": [{"id": "t1", "isResolved": False}],
                                "pageInfo": {
                                    "hasNextPage": False,
                                    "endCursor": None,
                                },
                            }
                        }
                    }
                }
            }
        )


def test_read_only_pr_diagnostic_rehearsal():
    client = DiagnosticClient()
    github = Controller(None, client=client)

    pull = github.pull("arthexis/gway", 1218)
    threads = github.review_threads("arthexis/gway", 1218, unresolved=True)
    checks = github.checks("arthexis/gway", pull["head"]["sha"])
    runs = github.runs("arthexis/gway", branch="feature/github-transport")
    jobs = github.jobs("arthexis/gway", runs[0]["id"])
    logs = github.job_logs("arthexis/gway", jobs[0]["id"])

    assert threads == [{"id": "t1", "isResolved": False}]
    assert checks[0]["conclusion"] == "failure"
    assert runs[0]["conclusion"] == "failure"
    assert jobs[0]["conclusion"] == "failure"
    assert "Ruff lint failed" in logs["content"]
