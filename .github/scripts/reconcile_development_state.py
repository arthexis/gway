#!/usr/bin/env python3
"""Reconcile deterministic GitHub development state for this repository."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from dataclasses import dataclass
from typing import Any

PARENT_RE = re.compile(
    r"(?im)\b(?:parent|closes|fixes|resolves)\s*:?[ \t]*(?:https://github\.com/[^/]+/[^/]+/issues/)?#?(\d+)\b"
)
MARKER_PREFIX = "<!-- development-state:pr="


@dataclass(frozen=True)
class ItemState:
    open: bool
    draft: bool
    approved: bool
    in_progress: bool
    on_hold: bool


def labels_from(item: dict[str, Any]) -> set[str]:
    labels = item.get("labels") or []
    result = set()
    for label in labels:
        name = label.get("name") if isinstance(label, dict) else str(label)
        result.add(name.casefold())
    return result


def parse_parent_issue(body: str | None) -> int | None:
    if not body:
        return None
    match = PARENT_RE.search(body)
    return int(match.group(1)) if match else None


class GitHub:
    def __init__(self, repository: str) -> None:
        self.repository = repository

    def _run(self, *args: str, check: bool = True) -> str:
        proc = subprocess.run(
            ["gh", *args],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if check and proc.returncode:
            raise RuntimeError(
                f"gh {' '.join(args)} failed ({proc.returncode}): {proc.stderr.strip()}"
            )
        return proc.stdout

    def api_json(self, endpoint: str) -> Any:
        return json.loads(self._run("api", endpoint))

    def ensure_eligible_label(self) -> None:
        endpoint = f"repos/{self.repository}/labels/eligible"
        proc = subprocess.run(
            ["gh", "api", endpoint],
            check=False,
            text=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if proc.returncode == 0:
            return
        self._run(
            "api",
            f"repos/{self.repository}/labels",
            "--method",
            "POST",
            "-f",
            "name=eligible",
            "-f",
            "color=FBCA04",
            "-f",
            "description=Automation may start work on this issue",
        )

    def add_label(self, number: int, label: str) -> None:
        self._run(
            "api",
            f"repos/{self.repository}/issues/{number}/labels",
            "--method",
            "POST",
            "-f",
            f"labels[]={label}",
        )

    def remove_label(self, number: int, label: str) -> None:
        self._run(
            "api",
            f"repos/{self.repository}/issues/{number}/labels/{label}",
            "--method",
            "DELETE",
            check=False,
        )

    def pr_ready(self, number: int) -> None:
        self._run("pr", "ready", str(number), "--repo", self.repository)

    def issue(self, number: int) -> dict[str, Any]:
        return self.api_json(f"repos/{self.repository}/issues/{number}")

    def pull(self, number: int) -> dict[str, Any]:
        return self.api_json(f"repos/{self.repository}/pulls/{number}")

    def open_pulls(self) -> list[dict[str, Any]]:
        return self.api_json(f"repos/{self.repository}/pulls?state=open&per_page=100")

    def comments(self, issue_number: int) -> list[dict[str, Any]]:
        return self.api_json(
            f"repos/{self.repository}/issues/{issue_number}/comments?per_page=100"
        )

    def add_comment(self, issue_number: int, body: str) -> None:
        self._run(
            "api",
            f"repos/{self.repository}/issues/{issue_number}/comments",
            "--method",
            "POST",
            "-f",
            f"body={body}",
        )

    def open_issues(self) -> list[dict[str, Any]]:
        raw = self._run(
            "issue",
            "list",
            "--repo",
            self.repository,
            "--state",
            "open",
            "--limit",
            "1000",
            "--json",
            "number,labels,state",
        )
        return json.loads(raw)


def active_parent_map(pulls: list[dict[str, Any]]) -> dict[int, list[int]]:
    result: dict[int, list[int]] = {}
    for pr in pulls:
        parent = parse_parent_issue(pr.get("body"))
        if parent is not None:
            result.setdefault(parent, []).append(int(pr["number"]))
    return result


def ensure_reciprocal_link(gh: GitHub, parent: int, pr: int) -> None:
    marker = f"{MARKER_PREFIX}{pr} -->"
    for comment in gh.comments(parent):
        if marker in (comment.get("body") or ""):
            return
    gh.add_comment(parent, f"{marker}\nImplementation PR: #{pr}\n")


def reconcile_pr(gh: GitHub, number: int) -> int | None:
    pr = gh.pull(number)
    labels = labels_from(pr)
    state = ItemState(
        open=pr.get("state") == "open",
        draft=bool(pr.get("draft")),
        approved="approved" in labels,
        in_progress="in-progress" in labels,
        on_hold="on-hold" in labels,
    )

    if state.on_hold:
        print(f"PR #{number}: on-hold; leaving development state unchanged.")
        return parse_parent_issue(pr.get("body"))

    if state.approved and state.open and state.draft:
        print(f"PR #{number}: approved; marking Ready for Review.")
        gh.pr_ready(number)

    if not state.open and state.in_progress:
        print(f"PR #{number}: closed; releasing stale in-progress claim.")
        gh.remove_label(number, "in-progress")

    parent = parse_parent_issue(pr.get("body"))
    if parent is not None:
        ensure_reciprocal_link(gh, parent, number)
        if state.open:
            # A linked PR removes the parent from the unstarted admission queue.
            gh.remove_label(parent, "eligible")
    return parent


def reconcile_issue(
    gh: GitHub, issue_number: int, active: dict[int, list[int]] | None = None
) -> None:
    issue = gh.issue(issue_number)
    if "pull_request" in issue:
        return

    if issue.get("state") != "open":
        gh.remove_label(issue_number, "eligible")
        gh.remove_label(issue_number, "in-progress")
        return

    labels = labels_from(issue)
    if "on-hold" in labels:
        print(f"Issue #{issue_number}: on-hold; leaving development state unchanged.")
        return

    if active is None:
        active = active_parent_map(gh.open_pulls())
    if active.get(issue_number):
        # eligible is an explicit admission gate for work not yet represented by a PR.
        gh.remove_label(issue_number, "eligible")


def reconcile_all(gh: GitHub) -> None:
    active = active_parent_map(gh.open_pulls())
    for issue in gh.open_issues():
        reconcile_issue(gh, int(issue["number"]), active)


def run_self_tests() -> None:
    assert parse_parent_issue("Parent: #1084") == 1084
    assert parse_parent_issue("Closes #12") == 12
    assert parse_parent_issue("no parent") is None
    print("development-state reconciler self-tests passed")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--pr", type=int)
    parser.add_argument("--issue", type=int)
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        run_self_tests()
        return

    repository = os.environ.get("GITHUB_REPOSITORY")
    if not repository:
        raise SystemExit("GITHUB_REPOSITORY is required")

    gh = GitHub(repository)
    gh.ensure_eligible_label()

    parent: int | None = None
    if args.pr is not None:
        parent = reconcile_pr(gh, args.pr)
    if args.issue is not None:
        reconcile_issue(gh, args.issue)
    if parent is not None:
        reconcile_issue(gh, parent)
    if args.all or (args.pr is None and args.issue is None):
        reconcile_all(gh)


if __name__ == "__main__":
    main()
