"""Read-only Watchtower coordination observations."""

DEFAULT_REPOSITORIES = ("arthexis/gway", "arthexis/arthexis")


class Controller:
    """Stable Watchtower-facing summaries over existing GitHub read operations."""

    def __init__(self, gateway):
        self.gateway = gateway

    def _repositories(self, repositories):
        values = tuple(str(value).strip() for value in repositories if str(value).strip())
        return values or DEFAULT_REPOSITORIES

    @property
    def github(self):
        return self.gateway._github_controller

    @staticmethod
    def _labels(pull):
        labels = pull.get("labels", ()) if isinstance(pull, dict) else ()
        values = []
        for label in labels:
            if isinstance(label, dict):
                name = label.get("name")
            else:
                name = label
            if name:
                values.append(str(name))
        return tuple(values)

    def queue_status(self, *repository, mutate=False):
        """Return coordinated open-PR queue state for Watchtower repositories."""
        del mutate
        results = []
        for name in self._repositories(repository):
            pulls = self.github.pulls(name, state="open")
            queued = []
            excluded = []
            for pull in pulls:
                labels = self._labels(pull)
                normalized = {label.casefold().replace(" ", "-") for label in labels}
                native_auto_merge = bool(pull.get("auto_merge"))
                item = {
                    "number": pull.get("number"),
                    "title": pull.get("title"),
                    "draft": bool(pull.get("draft", False)),
                    "labels": list(labels),
                    "head": (pull.get("head") or {}).get("sha"),
                    "base": (pull.get("base") or {}).get("ref"),
                    "deploy": "deploy" in normalized,
                    "auto_merge": native_auto_merge,
                    "authorized": native_auto_merge,
                }
                if "on-hold" in normalized:
                    excluded.append(item)
                else:
                    queued.append(item)
            results.append(
                {
                    "repository": name,
                    "queued": queued,
                    "excluded": excluded,
                    "queued_count": len(queued),
                    "excluded_count": len(excluded),
                    "clear": not queued,
                }
            )
        return results

    def deploy_status(self, *repository, mutate=False):
        """Return the latest Watchtower-related Actions run for each repository."""
        del mutate
        results = []
        for name in self._repositories(repository):
            runs = self.github.runs(name)
            relevant = [
                run
                for run in runs
                if "watchtower" in str(run.get("name", "")).casefold()
                or "watchtower" in str(run.get("path", "")).casefold()
            ]
            run = relevant[0] if relevant else None
            conclusion = None if run is None else run.get("conclusion")
            problem = conclusion in {
                "failure",
                "timed_out",
                "action_required",
                "startup_failure",
                "stale",
            }
            results.append(
                {
                    "repository": name,
                    "available": run is not None,
                    "problem": problem,
                    "run_id": None if run is None else run.get("id"),
                    "name": None if run is None else run.get("name"),
                    "event": None if run is None else run.get("event"),
                    "status": None if run is None else run.get("status"),
                    "conclusion": conclusion,
                    "head_sha": None if run is None else run.get("head_sha"),
                    "head_branch": None if run is None else run.get("head_branch"),
                    "created_at": None if run is None else run.get("created_at"),
                    "updated_at": None if run is None else run.get("updated_at"),
                    "url": None if run is None else run.get("html_url"),
                }
            )
        return results

    def release_status(self, *repository, mutate=False):
        """Return latest release and default-branch head for each repository."""
        del mutate
        results = []
        for name in self._repositories(repository):
            repository_status = self.github.status(name)
            branch_name = repository_status.get("default_branch")
            branch = self.github.branch(name, branch_name) if branch_name else {}
            release = self.github.latest_release(name)
            head_sha = ((branch.get("commit") or {}).get("sha")) if isinstance(branch, dict) else None
            target = release.get("target_commitish") if isinstance(release, dict) else None
            results.append(
                {
                    "repository": name,
                    "default_branch": branch_name,
                    "head_sha": head_sha,
                    "release_tag": release.get("tag_name") if isinstance(release, dict) else None,
                    "release_target": target,
                    "published_at": release.get("published_at") if isinstance(release, dict) else None,
                    "draft": bool(release.get("draft", False)) if isinstance(release, dict) else None,
                    "prerelease": bool(release.get("prerelease", False)) if isinstance(release, dict) else None,
                    "target_is_head": bool(target and head_sha and target == head_sha),
                }
            )
        return results


def register(gateway):
    """Register Watchtower-owned node-role observation operations."""
    controller = Controller(gateway)
    gateway._watchtower_controller = controller
    gateway.wrap(
        "node.watchtower.deploy.status",
        controller.deploy_status,
        op="status",
        sub="deploy",
    )
    gateway.wrap(
        "node.watchtower.release.status",
        controller.release_status,
        op="status",
        sub="release",
    )
    gateway.wrap(
        "node.watchtower.queue.status",
        controller.queue_status,
        op="status",
        sub="queue",
    )
    return controller
