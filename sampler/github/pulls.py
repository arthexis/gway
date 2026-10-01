"""GitHub pull-request operations."""

from __future__ import annotations


class PullOperations:
    def pulls(self, repository, state="open"):
        """List pull requests."""
        return self._all(
            f"{self._repo(repository)}/pulls",
            params={"state": state, "per_page": 100},
        )

    def pull(self, repository, number):
        """Return one pull request."""
        return self._github().request(
            "GET", f"{self._repo(repository)}/pulls/{int(number)}"
        ).data

    def create_pull(
        self, repository, title, head, base, body=None, draft=False, mutate=True
    ):
        """Create a GitHub pull request."""
        if not mutate:
            raise PermissionError("GitHub pull request mutation is disabled")
        payload = {
            "title": str(title),
            "head": str(head),
            "base": str(base),
            "draft": bool(draft),
        }
        if body is not None:
            payload["body"] = str(body)
        return self._github().request(
            "POST", f"{self._repo(repository)}/pulls", json=payload
        ).data

    def update_pull(
        self, repository, number, title=None, body=None, state=None, base=None,
        mutate=True
    ):
        """Update a GitHub pull request's ordinary collaboration fields."""
        if not mutate:
            raise PermissionError("GitHub pull request mutation is disabled")
        payload = {}
        if title is not None:
            payload["title"] = str(title)
        if body is not None:
            payload["body"] = str(body)
        if state is not None:
            state = str(state).lower()
            if state not in {"open", "closed"}:
                raise ValueError("pull request state must be open or closed")
            payload["state"] = state
        if base is not None:
            payload["base"] = str(base)
        if not payload:
            raise ValueError("pull request update requires title, body, state, or base")
        return self._github().request(
            "PATCH", f"{self._repo(repository)}/pulls/{int(number)}", json=payload
        ).data

    def close_pull(self, repository, number, mutate=True):
        """Close a GitHub pull request."""
        return self.update_pull(repository, number, state="closed", mutate=mutate)

    def reopen_pull(self, repository, number, mutate=True):
        """Reopen a GitHub pull request."""
        return self.update_pull(repository, number, state="open", mutate=mutate)

    def _pull_node_id(self, repository, number):
        pull = self.pull(repository, number)
        node_id = pull.get("node_id") if isinstance(pull, dict) else None
        if not node_id:
            raise ValueError("GitHub pull request response is missing node_id")
        return node_id

    def _pull_lifecycle(self, repository, number, mutation, field, mutate=True):
        if not mutate:
            raise PermissionError("GitHub pull request mutation is disabled")
        node_id = self._pull_node_id(repository, number)
        query = f"""
        mutation($id: ID!) {{
          {mutation}(input: {{pullRequestId: $id}}) {{
            pullRequest {{ id number isDraft url }}
          }}
        }}
        """
        payload = self._github().graphql(query, {"id": node_id}).data
        if payload.get("errors"):
            raise RuntimeError(f"GitHub GraphQL error: {payload['errors']}")
        return payload["data"][field]["pullRequest"]

    def ready_pull(self, repository, number, mutate=True):
        """Mark a draft pull request ready for review."""
        return self._pull_lifecycle(
            repository,
            number,
            "markPullRequestReadyForReview",
            "markPullRequestReadyForReview",
            mutate=mutate,
        )

    def draft_pull(self, repository, number, mutate=True):
        """Convert a pull request back to draft."""
        return self._pull_lifecycle(
            repository,
            number,
            "convertPullRequestToDraft",
            "convertPullRequestToDraft",
            mutate=mutate,
        )

    def merge_pull(
        self, repository, number, sha, method=None, title=None, message=None,
        mutate=True
    ):
        """Explicitly merge a pull request at the expected head SHA."""
        if not mutate:
            raise PermissionError("GitHub pull request mutation is disabled")
        if sha is None or not str(sha).strip():
            raise ValueError("expected pull request head sha is required")
        payload = {"sha": str(sha)}
        if method is not None:
            method = str(method).lower()
            if method not in {"merge", "squash", "rebase"}:
                raise ValueError("merge method must be merge, squash, or rebase")
            payload["merge_method"] = method
        if title is not None:
            payload["commit_title"] = str(title)
        if message is not None:
            payload["commit_message"] = str(message)
        return self._github().request(
            "PUT",
            f"{self._repo(repository)}/pulls/{int(number)}/merge",
            json=payload,
        ).data
