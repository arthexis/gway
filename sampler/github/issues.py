"""GitHub issue and label operations."""

from __future__ import annotations

from .base import segment


def _same_repository(issue, repository):
    """Return whether an embedded GitHub issue belongs to ``repository``."""
    expected = str(repository).strip("/").lower()
    embedded = ((issue.get("repository") or {}).get("full_name") or "").lower()
    if embedded:
        return embedded == expected
    repository_url = str(issue.get("repository_url") or "").rstrip("/").lower()
    return bool(repository_url) and repository_url.endswith(f"/repos/{expected}")


def _linked_pull(event, repository):
    """Normalize a same-repository PR from one GitHub cross-reference event."""
    if event.get("event") != "cross-referenced":
        return None
    source = event.get("source") or {}
    if source.get("type") != "issue":
        return None
    issue = source.get("issue") or {}
    pull = issue.get("pull_request")
    if not isinstance(pull, dict) or not _same_repository(issue, repository):
        return None
    number = issue.get("number")
    if number is None:
        return None
    return {
        "number": int(number),
        "title": issue.get("title"),
        "state": issue.get("state"),
        "draft": bool(issue.get("draft", False)),
        "merged_at": pull.get("merged_at"),
        "url": issue.get("html_url") or pull.get("html_url"),
        "relationship": "cross-referenced",
    }


class IssueOperations:
    def issues(self, repository, state="open"):
        """List issue records, including pull requests as GitHub returns them."""
        return self._all(
            f"{self._repo(repository)}/issues",
            params={"state": state, "per_page": 100},
        )

    def issue(self, repository, number):
        """Return one issue record."""
        return self._github().request(
            "GET", f"{self._repo(repository)}/issues/{int(number)}"
        ).data

    def issue_prs(self, repository, issue, state="open"):
        """Return PRs GitHub cross-references from an issue timeline.

        Linkage is intentionally provider-backed: this operation does not infer
        relationships from branch names, titles, body text, or model judgment.
        ``state`` accepts ``open``, ``closed``, or ``all`` and defaults to the
        active/open PRs that are useful to the Drive workflow.
        """
        state = str(state).lower()
        if state not in {"open", "closed", "all"}:
            raise ValueError("state must be open, closed, or all")
        events = self._all(
            f"{self._repo(repository)}/issues/{int(issue)}/timeline",
            params={"per_page": 100},
        )
        result = []
        seen = set()
        for event in events:
            pull = _linked_pull(event, repository)
            if pull is None or pull["number"] in seen:
                continue
            if state != "all" and pull["state"] != state:
                continue
            seen.add(pull["number"])
            result.append(pull)
        return result

    def comments(self, repository, number):
        """List conversation comments for an issue or pull request."""
        return self._all(
            f"{self._repo(repository)}/issues/{int(number)}/comments",
            params={"per_page": 100},
        )

    def create_issue(self, repository, title, body=None, mutate=True):
        """Create a GitHub issue."""
        if not mutate:
            raise PermissionError("GitHub issue mutation is disabled")
        payload = {"title": str(title)}
        if body is not None:
            payload["body"] = str(body)
        return self._github().request(
            "POST", f"{self._repo(repository)}/issues", json=payload
        ).data

    def update_issue(
        self, repository, number, title=None, body=None, state=None, mutate=True
    ):
        """Update a GitHub issue's ordinary collaboration fields."""
        if not mutate:
            raise PermissionError("GitHub issue mutation is disabled")
        payload = {}
        if title is not None:
            payload["title"] = str(title)
        if body is not None:
            payload["body"] = str(body)
        if state is not None:
            state = str(state).lower()
            if state not in {"open", "closed"}:
                raise ValueError("issue state must be open or closed")
            payload["state"] = state
        if not payload:
            raise ValueError("issue update requires title, body, or state")
        return self._github().request(
            "PATCH", f"{self._repo(repository)}/issues/{int(number)}", json=payload
        ).data

    def close_issue(self, repository, number, mutate=True):
        """Close a GitHub issue."""
        return self.update_issue(repository, number, state="closed", mutate=mutate)

    def reopen_issue(self, repository, number, mutate=True):
        """Reopen a GitHub issue."""
        return self.update_issue(repository, number, state="open", mutate=mutate)

    def comment_issue(self, repository, number, body, mutate=True):
        """Create a conversation comment on an issue or pull request."""
        if not mutate:
            raise PermissionError("GitHub issue mutation is disabled")
        return self._github().request(
            "POST",
            f"{self._repo(repository)}/issues/{int(number)}/comments",
            json={"body": str(body)},
        ).data

    def add_labels(self, repository, number, *labels, mutate=True):
        """Add labels to an issue or pull request."""
        if not mutate:
            raise PermissionError("GitHub label mutation is disabled")
        values = [str(label) for label in labels if str(label)]
        if not values:
            raise ValueError("at least one label is required")
        return self._github().request(
            "POST",
            f"{self._repo(repository)}/issues/{int(number)}/labels",
            json={"labels": values},
        ).data

    def remove_label(self, repository, number, label, mutate=True):
        """Remove one label from an issue or pull request."""
        if not mutate:
            raise PermissionError("GitHub label mutation is disabled")
        if not str(label):
            raise ValueError("label is required")
        return self._github().request(
            "DELETE",
            f"{self._repo(repository)}/issues/{int(number)}/labels/{segment(label)}",
        ).data