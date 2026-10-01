"""Shared deterministic GitHub test evidence for sampler capability tests.

The harness models provider facts, not lifecycle policy. Tests configure evidence
and assert public contracts so lifecycle ordering can evolve without duplicating
large fake controllers in every test module.
"""

from __future__ import annotations

import base64
import json

from sampler.github.status import Controller


REPOSITORY = "arthexis/gway"
PULL = 10


def pull_request(**updates):
    value = {
        "number": PULL,
        "state": "open",
        "draft": False,
        "merged": False,
        "merge_commit_sha": None,
        "mergeable": True,
        "mergeable_state": "clean",
        "auto_merge": None,
        "labels": [],
        "base": {"ref": "main", "sha": "base"},
        "head": {"ref": "feature", "sha": "head"},
        "html_url": f"https://github.com/{REPOSITORY}/pull/{PULL}",
    }
    value.update(updates)
    return value


class GitHubEvidenceController(Controller):
    """One configurable provider/evidence harness for GitHub package tests."""

    def __init__(self, **evidence):
        super().__init__(None, client=object())
        self.pr_data = evidence.pop("pr", pull_request())
        self.review_items = evidence.pop("reviews", [])
        self.thread_items = evidence.pop("threads", [])
        self.review_decision_value = evidence.pop("decision", None)
        self.compare_result = evidence.pop(
            "compare", {"status": "ahead", "ahead_by": 1, "behind_by": 0}
        )
        self.issue_targets = evidence.pop("issue_targets", [10, 11])
        self.issue_state_calls = []
        self.check_items = evidence.pop(
            "checks",
            [
                {
                    "id": 5,
                    "name": "python / Python compatibility",
                    "conclusion": "success",
                }
            ],
        )
        self.annotation_items = evidence.pop(
            "annotations",
            [{"path": "tests/test_example.py", "message": "assertion failed"}],
        )
        self.job_items = evidence.pop(
            "jobs",
            [
                {"id": 20, "run_id": 30, "name": "tests", "conclusion": "failure"},
                {"id": 21, "run_id": 30, "name": "compat", "conclusion": "success"},
            ],
        )
        self.on_main = evidence.pop("on_main", True)
        self.accepted = evidence.pop("accepted", True)
        self.watchtower_stages = evidence.pop(
            "watchtower_stages", ["0-gway", "1-arthexis", "2-remote"]
        )
        if evidence:
            raise TypeError(f"unsupported evidence keys: {sorted(evidence)}")

    def pull(self, repository, number):
        return dict(self.pr_data)

    def repository(self, repository):
        return {
            "full_name": repository,
            "default_branch": "main",
            "private": False,
            "archived": False,
            "disabled": False,
        }

    def branch(self, repository, branch):
        return {"name": branch, "commit": {"sha": "main-sha"}}

    def issue_prs(self, repository, issue, state="open"):
        self.issue_state_calls.append(state)
        return [{"number": number} for number in self.issue_targets]

    def reviews(self, repository, number):
        return list(self.review_items)

    def review_threads(self, repository, number, unresolved=False):
        return list(self.thread_items)

    def review_decision(self, repository, number):
        return self.review_decision_value

    def review_comments(self, repository, number):
        return [{"id": 2, "body": "Please adjust this"}]

    def compare(self, repository, base, head):
        if head == "main-sha":
            return {"status": "ahead" if self.on_main else "diverged"}
        if head == "accepted-sha":
            return {"status": "ahead" if self.accepted else "diverged"}
        return dict(self.compare_result)

    def file(self, repository, path, ref=None):
        manifest = {
            "accepted_at": "2026-09-30T21:24:49+00:00",
            "arthexis_sha": "accepted-sha",
            "gway_sha": "accepted-sha",
            "run_id": "123",
            "run_url": "https://github.com/arthexis/arthexis/actions/runs/123",
            "stages": list(self.watchtower_stages),
        }
        content = base64.b64encode(json.dumps(manifest).encode()).decode()
        return {"encoding": "base64", "content": content}

    def checks(self, repository, ref):
        return list(self.check_items)

    def check_annotations(self, repository, check):
        return list(self.annotation_items)

    def run(self, repository, run):
        return {
            "id": int(run),
            "name": "Python compatibility",
            "status": "completed",
            "conclusion": "failure",
            "head_sha": "head",
        }

    def jobs(self, repository, run):
        return list(self.job_items)

    def job(self, repository, job):
        for item in self.job_items:
            if int(item["id"]) == int(job):
                value = dict(item)
                value.setdefault("steps", [{"name": "pytest", "conclusion": value.get("conclusion")}])
                return value
        raise KeyError(job)

    def job_logs(self, repository, job):
        return {
            "status": 200,
            "content_type": "text/plain",
            "content": b"failure details\n",
        }

    def artifacts(self, repository, run, name=None):
        return [{"id": 40, "name": "gway-ci-result"}]

    def artifact_json(self, repository, artifact, filename="ci-result.json"):
        return {"state": "failed", "phase": "tests"}
