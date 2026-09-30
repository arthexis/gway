#!/usr/bin/env python3
"""Resolve PR dependencies that require successful Watchtower certification."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

LABEL = "needs-watchtower"
HEADER = re.compile(
    r"(?im)^Watchtower-Depends-On:\s*(arthexis/(?:gway|arthexis))#(\d+)\s*$"
)
STATE_REPO = "arthexis/arthexis"
STATE_PATH = ".watchtower/accepted.json"
STATE_REF = "watchtower-state"


class DependencyError(RuntimeError):
    pass


def request(path: str):
    token = os.environ.get("GH_TOKEN", "")
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        f"https://api.github.com/{path.lstrip('/')}",
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise DependencyError(f"GitHub API {exc.code} for {path}: {detail}") from exc


def dependency_from_body(body: str | None):
    matches = HEADER.findall(body or "")
    if not matches:
        return None
    if len(matches) != 1:
        raise DependencyError(
            "needs-watchtower PR must contain exactly one Watchtower-Depends-On header"
        )
    repo, number = matches[0]
    return repo, int(number)


def pull(repo: str, number: int):
    return request(f"repos/{repo}/pulls/{number}")


def dependency_chain(repo: str, number: int):
    seen = []
    current = (repo, number)
    while True:
        if current in seen:
            cycle = " -> ".join(f"{r}#{n}" for r, n in [*seen, current])
            raise DependencyError(f"Watchtower dependency cycle: {cycle}")
        seen.append(current)
        pr = pull(*current)
        dependency = dependency_from_body(pr.get("body"))
        if dependency is None:
            return seen
        current = dependency


def accepted_manifest():
    payload = request(
        f"repos/{STATE_REPO}/contents/{STATE_PATH}?ref={urllib.parse.quote(STATE_REF)}"
    )
    return json.loads(base64.b64decode(payload["content"]).decode())


def accepted_contains(repo: str, merge_sha: str, manifest: dict):
    key = "gway_sha" if repo == "arthexis/gway" else "arthexis_sha"
    accepted = manifest.get(key, "")
    if not re.fullmatch(r"[0-9a-f]{40}", accepted or ""):
        raise DependencyError(f"accepted manifest has no valid {key}")
    comparison = request(f"repos/{repo}/compare/{merge_sha}...{accepted}")
    return comparison.get("status") in {"identical", "ahead"}, accepted


def evaluate(repo: str, number: int):
    pr = pull(repo, number)
    labels = {item["name"].lower() for item in pr.get("labels", [])}
    if LABEL not in labels:
        return {"status": "not-applicable", "repo": repo, "number": number}

    dependency = dependency_from_body(pr.get("body"))
    if dependency is None:
        raise DependencyError(
            "needs-watchtower PR is missing Watchtower-Depends-On: arthexis/<repo>#<number>"
        )

    dependency_chain(repo, number)
    dep_repo, dep_number = dependency
    dep = pull(dep_repo, dep_number)
    if not dep.get("merged_at"):
        return {
            "status": "waiting-merge",
            "repo": repo,
            "number": number,
            "dependency": f"{dep_repo}#{dep_number}",
        }

    merge_sha = dep.get("merge_commit_sha") or ""
    if not re.fullmatch(r"[0-9a-f]{40}", merge_sha):
        raise DependencyError(
            f"dependency {dep_repo}#{dep_number} has no valid merge commit SHA"
        )

    manifest = accepted_manifest()
    satisfied, accepted = accepted_contains(dep_repo, merge_sha, manifest)
    return {
        "status": "satisfied" if satisfied else "waiting-watchtower",
        "repo": repo,
        "number": number,
        "dependency": f"{dep_repo}#{dep_number}",
        "dependency_merge_sha": merge_sha,
        "accepted_sha": accepted,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("repo")
    parser.add_argument("number", type=int)
    args = parser.parse_args()
    try:
        result = evaluate(args.repo, args.number)
    except DependencyError as exc:
        result = {
            "status": "invalid",
            "repo": args.repo,
            "number": args.number,
            "error": str(exc),
        }
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(2 if result["status"] == "invalid" else 0)


if __name__ == "__main__":
    main()
