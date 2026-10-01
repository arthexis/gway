"""GitHub release operations."""

from __future__ import annotations

from .base import segment


class ReleaseOperations:
    def releases(self, repository):
        """List repository releases."""
        return self._all(
            f"{self._repo(repository)}/releases",
            params={"per_page": 100},
        )

    def release(self, repository, release):
        """Return one repository release by numeric ID."""
        return self._github().request(
            "GET", f"{self._repo(repository)}/releases/{int(release)}"
        ).data

    def release_tag(self, repository, tag):
        """Return one repository release by tag."""
        return self._github().request(
            "GET", f"{self._repo(repository)}/releases/tags/{segment(tag)}"
        ).data

    def latest_release(self, repository):
        """Return the repository's latest published release."""
        return self._github().request(
            "GET", f"{self._repo(repository)}/releases/latest"
        ).data

    def create_release(
        self,
        repository,
        tag,
        target=None,
        name=None,
        body=None,
        draft=False,
        prerelease=False,
        mutate=True,
    ):
        """Create a GitHub release for an explicit tag."""
        if not mutate:
            raise PermissionError("GitHub release mutation is disabled")
        if not str(tag):
            raise ValueError("release tag is required")
        payload = {
            "tag_name": str(tag),
            "draft": bool(draft),
            "prerelease": bool(prerelease),
        }
        if target is not None:
            payload["target_commitish"] = str(target)
        if name is not None:
            payload["name"] = str(name)
        if body is not None:
            payload["body"] = str(body)
        return self._github().request(
            "POST", f"{self._repo(repository)}/releases", json=payload
        ).data

    def update_release(
        self,
        repository,
        release,
        tag=None,
        target=None,
        name=None,
        body=None,
        draft=None,
        prerelease=None,
        mutate=True,
    ):
        """Update a GitHub release by explicit numeric release ID."""
        if not mutate:
            raise PermissionError("GitHub release mutation is disabled")
        payload = {}
        if tag is not None:
            if not str(tag):
                raise ValueError("release tag cannot be empty")
            payload["tag_name"] = str(tag)
        if target is not None:
            payload["target_commitish"] = str(target)
        if name is not None:
            payload["name"] = str(name)
        if body is not None:
            payload["body"] = str(body)
        if draft is not None:
            payload["draft"] = bool(draft)
        if prerelease is not None:
            payload["prerelease"] = bool(prerelease)
        if not payload:
            raise ValueError("release update requires at least one field")
        return self._github().request(
            "PATCH",
            f"{self._repo(repository)}/releases/{int(release)}",
            json=payload,
        ).data
