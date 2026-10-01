"""PR rollout checks from merge through Watchtower certification."""

from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
import json

from .observe import Controller as ObserveController


_WATCHTOWER_REPOSITORY = "arthexis/arthexis"
_WATCHTOWER_REF = "watchtower-state"
_WATCHTOWER_MANIFEST = ".watchtower/accepted.json"
_WATCHTOWER_SHA_FIELDS = {
    "arthexis/gway": "gway_sha",
    "arthexis/arthexis": "arthexis_sha",
}
_WATCHTOWER_REQUIRED_STAGE = {
    "arthexis/gway": "0-gway",
    "arthexis/arthexis": "1-arthexis",
}


def _ancestor(compare):
    """Whether compare(base, head) proves base is contained in head."""
    return isinstance(compare, dict) and compare.get("status") in {"ahead", "identical"}


class Controller(ObserveController):
    """GitHub evidence plus deterministic PR rollout state."""

    def _accepted_watchtower(self):
        raw = self.file(
            _WATCHTOWER_REPOSITORY,
            _WATCHTOWER_MANIFEST,
            ref=_WATCHTOWER_REF,
        )
        if not isinstance(raw, dict):
            raise TypeError("Watchtower accepted manifest response must be an object")
        content = raw.get("content")
        if content is None:
            raise ValueError("Watchtower accepted manifest is missing content")
        encoding = str(raw.get("encoding") or "").lower()
        if encoding == "base64":
            content = base64.b64decode(str(content)).decode("utf-8")
        manifest = json.loads(content)
        if not isinstance(manifest, dict):
            raise TypeError("Watchtower accepted manifest must contain a JSON object")
        return manifest

    def _run_rollout(self, operation, repository, pulls, *, issue=None, serial=False):
        targets = [int(pull) for pull in pulls]
        if issue is not None:
            if targets:
                raise ValueError("pull targets and --issue are mutually exclusive")
            targets = [
                int(item["number"])
                for item in self.issue_prs(repository, int(issue), state="all")
            ]
        if not targets:
            raise ValueError("at least one pull target or --issue is required")
        if len(targets) == 1 and issue is None:
            return operation(repository, targets[0])
        if serial or len(targets) == 1:
            results = [operation(repository, pull) for pull in targets]
        else:
            with ThreadPoolExecutor(max_workers=min(8, len(targets))) as executor:
                results = list(executor.map(lambda pull: operation(repository, pull), targets))
        result = {"repository": str(repository), "targets": targets, "pulls": results}
        if issue is not None:
            result["issue"] = int(issue)
        return result

    def check_rollout(self, repository, *pulls, issue=None, serial=False):
        """Return merge/main/Watchtower certification state for PR targets."""
        return self._run_rollout(
            self._check_rollout_pull,
            repository,
            pulls,
            issue=issue,
            serial=serial,
        )

    def _check_rollout_pull(self, repository, pull):
        repository = str(repository)
        pr = self.pull(repository, pull)
        merged = bool(pr.get("merged"))
        merge_sha = pr.get("merge_commit_sha")

        repo = self.repository(repository)
        default_branch = repo.get("default_branch") if isinstance(repo, dict) else None
        branch = self.branch(repository, default_branch) if default_branch else {}
        main_sha = ((branch.get("commit") or {}).get("sha")) if isinstance(branch, dict) else None

        on_main = False
        if merged and merge_sha and main_sha:
            on_main = _ancestor(self.compare(repository, merge_sha, main_sha))

        required_stage = _WATCHTOWER_REQUIRED_STAGE.get(repository)
        watchtower = {
            "available": repository in _WATCHTOWER_SHA_FIELDS,
            "certified": False,
            "required_stage": required_stage,
            "accepted_sha": None,
            "accepted_at": None,
            "run_id": None,
            "run_url": None,
            "stages": [],
        }
        if on_main and watchtower["available"]:
            manifest = self._accepted_watchtower()
            accepted_sha = manifest.get(_WATCHTOWER_SHA_FIELDS[repository])
            stages = list(manifest.get("stages") or ())
            watchtower.update(
                {
                    "accepted_sha": accepted_sha,
                    "accepted_at": manifest.get("accepted_at"),
                    "run_id": manifest.get("run_id"),
                    "run_url": manifest.get("run_url"),
                    "stages": stages,
                }
            )
            accepted_contains_pr = bool(
                merge_sha
                and accepted_sha
                and _ancestor(self.compare(repository, merge_sha, accepted_sha))
            )
            watchtower["certified"] = bool(
                accepted_contains_pr
                and (required_stage is None or required_stage in stages)
            )

        if not merged:
            state = "open" if pr.get("state") == "open" else "closed"
        elif not on_main:
            state = "merged-not-main"
        elif watchtower["certified"]:
            state = "certified"
        else:
            state = "on-main"

        result = {
            "repository": repository,
            "pr": int(pull),
            "state": state,
            "merged": {"value": merged, "sha": merge_sha},
            "main": {
                "value": on_main,
                "branch": default_branch,
                "sha": main_sha,
            },
            "watchtower": watchtower,
        }
        if state == "merged-not-main":
            result["diagnostic_target"] = {
                "kind": "github-rollout",
                "pr": int(pull),
                "stage": "main",
            }
        elif state == "on-main" and watchtower["available"]:
            result["diagnostic_target"] = {
                "kind": "github-rollout",
                "pr": int(pull),
                "stage": "watchtower",
            }
        return result

    def observe_rollout(self, repository, *pulls, issue=None, serial=False):
        """Expand rollout state into ancestry and Watchtower acceptance evidence."""
        return self._run_rollout(
            self._observe_rollout_pull,
            repository,
            pulls,
            issue=issue,
            serial=serial,
        )

    def _observe_rollout_pull(self, repository, pull):
        repository = str(repository)
        check = self._check_rollout_pull(repository, pull)
        pr = self.pull(repository, pull)
        merge_sha = check["merged"]["sha"]
        main_sha = check["main"]["sha"]
        accepted_sha = check["watchtower"]["accepted_sha"]

        main_compare = (
            self.compare(repository, merge_sha, main_sha)
            if merge_sha and main_sha
            else None
        )
        certification_compare = (
            self.compare(repository, merge_sha, accepted_sha)
            if merge_sha and accepted_sha
            else None
        )
        manifest = self._accepted_watchtower() if check["watchtower"]["available"] else None

        return {
            "repository": repository,
            "pr": int(pull),
            "check": check,
            "pull": pr,
            "main_compare": main_compare,
            "watchtower_manifest": manifest,
            "certification_compare": certification_compare,
        }
