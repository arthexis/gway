from types import SimpleNamespace

from gway import Gateway
from gway.watchtower import Controller, DEFAULT_REPOSITORIES


class FakeGitHub:
    def __init__(self):
        self.calls = []
        self.job_records = []
        self.job_log_content = ""

    def jobs(self, repository, run):
        self.calls.append(("jobs", repository, run))
        return list(self.job_records)

    def job_logs(self, repository, job):
        self.calls.append(("job_logs", repository, job))
        return {"content": self.job_log_content}

    def pulls(self, repository, state="open"):
        self.calls.append(("pulls", repository, state))
        return [
            {
                "number": 1,
                "title": "Ready work",
                "draft": True,
                "labels": [{"name": "deploy"}],
                "auto_merge": {"merge_method": "merge"},
                "head": {"sha": "abc"},
                "base": {"ref": "main"},
            },
            {
                "number": 2,
                "title": "Paused",
                "draft": False,
                "labels": [{"name": "on hold"}],
                "auto_merge": None,
                "head": {"sha": "def"},
                "base": {"ref": "main"},
            },
        ]

    def runs(self, repository):
        self.calls.append(("runs", repository))
        return [
            {
                "id": 20,
                "name": "Quality",
                "path": ".github/workflows/quality.yml",
                "status": "completed",
                "conclusion": "success",
            },
            {
                "id": 21,
                "name": "Watchtower candidate",
                "path": ".github/workflows/watchtower-candidate.yml",
                "event": "push",
                "status": "completed",
                "conclusion": "success",
                "head_sha": "abc",
                "head_branch": "main",
                "created_at": "2026-09-28T00:00:00Z",
                "updated_at": "2026-09-28T00:01:00Z",
                "html_url": "https://example.invalid/run/21",
            },
        ]

    def status(self, repository):
        self.calls.append(("status", repository))
        return {
            "repository": repository,
            "default_branch": "main",
        }

    def branch(self, repository, branch):
        self.calls.append(("branch", repository, branch))
        return {"commit": {"sha": "abc"}}

    def latest_release(self, repository):
        self.calls.append(("latest_release", repository))
        return {
            "tag_name": "v1.2.3",
            "target_commitish": "abc",
            "published_at": "2026-09-28T00:02:00Z",
            "draft": False,
            "prerelease": False,
        }


def _controller():
    gateway = SimpleNamespace(_github_controller=FakeGitHub())
    return Controller(gateway), gateway._github_controller


def test_watchtower_queue_status_preserves_queue_policy():
    controller, github = _controller()

    result = controller.queue_status("arthexis/gway")

    assert result == [
        {
            "repository": "arthexis/gway",
            "queued": [
                {
                    "number": 1,
                    "title": "Ready work",
                    "draft": True,
                    "labels": ["deploy"],
                    "head": "abc",
                    "base": "main",
                    "deploy": True,
                    "auto_merge": True,
                    "authorized": True,
                }
            ],
            "excluded": [
                {
                    "number": 2,
                    "title": "Paused",
                    "draft": False,
                    "labels": ["on hold"],
                    "head": "def",
                    "base": "main",
                    "deploy": False,
                    "auto_merge": False,
                    "authorized": False,
                }
            ],
            "queued_count": 1,
            "excluded_count": 1,
            "clear": False,
        }
    ]
    assert github.calls == [("pulls", "arthexis/gway", "open")]


def test_watchtower_queue_status_defaults_to_coordinated_repositories():
    controller, github = _controller()

    result = controller.queue_status()

    assert [item["repository"] for item in result] == list(DEFAULT_REPOSITORIES)
    assert [call[1] for call in github.calls] == list(DEFAULT_REPOSITORIES)


def test_watchtower_deploy_status_selects_latest_relevant_run():
    controller, _ = _controller()

    result = controller.deploy_status("arthexis/gway")

    assert result == [
        {
            "repository": "arthexis/gway",
            "available": True,
            "problem": False,
            "failure": None,
            "run_id": 21,
            "name": "Watchtower candidate",
            "event": "push",
            "status": "completed",
            "conclusion": "success",
            "head_sha": "abc",
            "head_branch": "main",
            "created_at": "2026-09-28T00:00:00Z",
            "updated_at": "2026-09-28T00:01:00Z",
            "url": "https://example.invalid/run/21",
        }
    ]


def test_watchtower_deploy_status_handles_no_relevant_run():
    controller, github = _controller()
    github.runs = lambda repository: [{"id": 1, "name": "Quality"}]

    result = controller.deploy_status("arthexis/gway")

    assert result[0]["available"] is False
    assert result[0]["problem"] is False
    assert result[0]["failure"] is None
    assert result[0]["run_id"] is None


def test_watchtower_release_status_compares_release_target_to_head():
    controller, _ = _controller()

    result = controller.release_status("arthexis/gway")

    assert result == [
        {
            "repository": "arthexis/gway",
            "default_branch": "main",
            "head_sha": "abc",
            "release_tag": "v1.2.3",
            "release_target": "abc",
            "published_at": "2026-09-28T00:02:00Z",
            "draft": False,
            "prerelease": False,
            "target_is_head": True,
        }
    ]


def test_watchtower_node_operations_are_registered_and_read_only(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "demo"

[tool.gway.variables]
role = "watchtower"
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    gateway = Gateway()
    fake = FakeGitHub()
    gateway._watchtower_controller.gateway._github_controller = fake

    queue = gateway.execute("node queue status arthexis/gway", mutate=False)
    deploy = gateway.execute("node deploy status arthexis/gway", mutate=False)
    release = gateway.execute("node release status arthexis/gway", mutate=False)

    assert queue[0]["repository"] == "arthexis/gway"
    assert deploy[0]["run_id"] == 21
    assert release[0]["release_tag"] == "v1.2.3"
    for name in (
        "node.watchtower.queue.status",
        "node.watchtower.deploy.status",
        "node.watchtower.release.status",
    ):
        assert gateway.ops.resolve(name).mutates is False


def test_watchtower_deploy_status_marks_failed_latest_run_as_problem():
    controller, github = _controller()
    github.runs = lambda repository: [
        {
            "id": 620,
            "name": "Watchtower Deploy",
            "path": ".github/workflows/watchtower-deploy.yml",
            "event": "repository_dispatch",
            "status": "completed",
            "conclusion": "failure",
            "head_sha": "deadbeef",
            "head_branch": "main",
            "created_at": "2026-09-30T04:31:30Z",
            "updated_at": "2026-09-30T04:32:26Z",
            "html_url": "https://example.invalid/run/620",
        }
    ]

    github.job_records = [
        {
            "id": 9001,
            "name": "Watchtower Deploy",
            "conclusion": "failure",
            "steps": [
                {"name": "Converge public Gway bootstrap", "conclusion": "failure"},
                {"name": "Restore previous Gway runtime", "conclusion": "success"},
            ],
        }
    ]
    github.job_log_content = """
Traceback (most recent call last):
subprocess.CalledProcessError: Command ('sudo', '/usr/sbin/nginx', '-t') returned non-zero exit status 1.
##[error]Process completed with exit code 1.
gway_runtime_rollback=restored
"""

    result = controller.deploy_status("arthexis/arthexis")

    assert result[0]["run_id"] == 620
    assert result[0]["conclusion"] == "failure"
    assert result[0]["problem"] is True
    assert result[0]["failure"]["jobs"] == [
        {
            "job_id": 9001,
            "name": "Watchtower Deploy",
            "failed_steps": ["Converge public Gway bootstrap"],
        }
    ]
    excerpt = "\n".join(result[0]["failure"]["excerpt"])
    assert "nginx" in excerpt
    assert "CalledProcessError" in excerpt
    assert "exit code 1" in excerpt


def test_watchtower_deploy_status_does_not_treat_cancelled_latest_run_as_failure():
    controller, github = _controller()
    github.runs = lambda repository: [
        {
            "id": 621,
            "name": "Watchtower Deploy",
            "path": ".github/workflows/watchtower-deploy.yml",
            "status": "completed",
            "conclusion": "cancelled",
        }
    ]

    result = controller.deploy_status("arthexis/arthexis")

    assert result[0]["conclusion"] == "cancelled"
    assert result[0]["problem"] is False
    assert result[0]["failure"] is None
    assert not any(call[0] == "jobs" for call in github.calls)
