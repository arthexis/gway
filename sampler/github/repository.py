"""GitHub repository, commit, file, ref, branch, and tag operations."""

from __future__ import annotations

import base64
from urllib.parse import quote

from .base import segment


class RepositoryOperations:
    def repository(self, repository):
        """Return GitHub repository metadata."""
        return self._github().request("GET", self._repo(repository)).data

    def status(self, repository):
        """Return compact GitHub repository/source-control status."""
        repo = self.repository(repository)
        branch = repo.get("default_branch") if isinstance(repo, dict) else None
        return {
            "repository": repo.get("full_name") if isinstance(repo, dict) else repository,
            "default_branch": branch,
            "private": repo.get("private") if isinstance(repo, dict) else None,
            "archived": repo.get("archived") if isinstance(repo, dict) else None,
            "disabled": repo.get("disabled") if isinstance(repo, dict) else None,
            "pushed_at": repo.get("pushed_at") if isinstance(repo, dict) else None,
        }

    def branches(self, repository, protected=None):
        """List repository branches."""
        params = {"per_page": 100}
        if protected is not None:
            params["protected"] = str(bool(protected)).lower()
        return self._all(f"{self._repo(repository)}/branches", params=params)

    def branch(self, repository, branch):
        """Return one repository branch."""
        return self._github().request(
            "GET", f"{self._repo(repository)}/branches/{segment(branch)}"
        ).data

    def commits(self, repository, branch=None, path=None):
        """List repository commits, optionally filtered by branch or path."""
        params = {"per_page": 100}
        if branch is not None:
            params["sha"] = branch
        if path is not None:
            params["path"] = path
        return self._all(f"{self._repo(repository)}/commits", params=params)

    def commit(self, repository, commit):
        """Return one repository commit."""
        return self._github().request(
            "GET", f"{self._repo(repository)}/commits/{segment(commit)}"
        ).data

    def compare(self, repository, base, head):
        """Compare two commits/refs using GitHub's native compare result."""
        return self._github().request(
            "GET",
            f"{self._repo(repository)}/compare/{segment(base)}...{segment(head)}",
        ).data

    def file(self, repository, path, ref=None):
        """Return repository file or directory metadata/content."""
        params = {"ref": ref} if ref is not None else None
        encoded = quote(str(path).strip("/"), safe="/")
        return self._github().request(
            "GET", f"{self._repo(repository)}/contents/{encoded}", params=params
        ).data

    def create_file(self, repository, path, content, message, branch=None, mutate=True):
        """Create a repository file with an explicit commit message."""
        if not mutate:
            raise PermissionError("GitHub file mutation is disabled")
        encoded = quote(str(path).strip("/"), safe="/")
        if not encoded:
            raise ValueError("repository file path is required")
        if not str(message):
            raise ValueError("repository file commit message is required")
        payload = {
            "message": str(message),
            "content": base64.b64encode(
                content if isinstance(content, bytes) else str(content).encode()
            ).decode(),
        }
        if branch is not None:
            payload["branch"] = str(branch)
        return self._github().request(
            "PUT", f"{self._repo(repository)}/contents/{encoded}", json=payload
        ).data

    def update_file(
        self, repository, path, content, message, sha, branch=None, mutate=True
    ):
        """Update a repository file only at the expected blob SHA."""
        if not mutate:
            raise PermissionError("GitHub file mutation is disabled")
        if not str(sha):
            raise ValueError("repository file SHA is required")
        encoded = quote(str(path).strip("/"), safe="/")
        if not encoded:
            raise ValueError("repository file path is required")
        if not str(message):
            raise ValueError("repository file commit message is required")
        payload = {
            "message": str(message),
            "content": base64.b64encode(
                content if isinstance(content, bytes) else str(content).encode()
            ).decode(),
            "sha": str(sha),
        }
        if branch is not None:
            payload["branch"] = str(branch)
        return self._github().request(
            "PUT", f"{self._repo(repository)}/contents/{encoded}", json=payload
        ).data

    def delete_file(self, repository, path, message, sha, branch=None, mutate=True):
        """Delete a repository file only at the expected blob SHA."""
        if not mutate:
            raise PermissionError("GitHub file mutation is disabled")
        if not str(sha):
            raise ValueError("repository file SHA is required")
        encoded = quote(str(path).strip("/"), safe="/")
        if not encoded:
            raise ValueError("repository file path is required")
        if not str(message):
            raise ValueError("repository file commit message is required")
        payload = {"message": str(message), "sha": str(sha)}
        if branch is not None:
            payload["branch"] = str(branch)
        return self._github().request(
            "DELETE", f"{self._repo(repository)}/contents/{encoded}", json=payload
        ).data

    def tree(self, repository, tree, recursive=False):
        """Return a Git tree."""
        params = {"recursive": "1"} if recursive else None
        return self._github().request(
            "GET", f"{self._repo(repository)}/git/trees/{segment(tree)}", params=params
        ).data

    def ref(self, repository, ref):
        """Return one Git reference."""
        encoded = quote(str(ref).removeprefix("refs/"), safe="/")
        return self._github().request(
            "GET", f"{self._repo(repository)}/git/ref/{encoded}"
        ).data

    def refs(self, repository, namespace=None):
        """List Git references, optionally below a namespace."""
        suffix = "/"
        if namespace:
            suffix += quote(str(namespace).removeprefix("refs/"), safe="/")
        return self._all(f"{self._repo(repository)}/git/matching-refs{suffix}")

    def create_ref(self, repository, ref, sha, mutate=True):
        """Create a Git reference at an explicit commit SHA."""
        if not mutate:
            raise PermissionError("GitHub reference mutation is disabled")
        ref = str(ref)
        sha = str(sha)
        if not ref:
            raise ValueError("Git reference is required")
        if not sha:
            raise ValueError("Git reference SHA is required")
        full_ref = ref if ref.startswith("refs/") else f"refs/{ref}"
        return self._github().request(
            "POST", f"{self._repo(repository)}/git/refs", json={"ref": full_ref, "sha": sha}
        ).data

    def create_branch(self, repository, branch, sha, mutate=True):
        """Create a branch at an explicit commit SHA."""
        branch = str(branch).removeprefix("refs/heads/")
        if not branch:
            raise ValueError("Git branch is required")
        return self.create_ref(repository, f"refs/heads/{branch}", sha, mutate=mutate)

    def delete_ref(self, repository, ref, mutate=True):
        """Delete an explicit Git reference."""
        if not mutate:
            raise PermissionError("GitHub reference mutation is disabled")
        ref = str(ref).removeprefix("refs/")
        if not ref:
            raise ValueError("Git reference is required")
        self._github().request(
            "DELETE", f"{self._repo(repository)}/git/refs/{quote(ref, safe='/')}"
        )
        return {"repository": str(repository), "ref": f"refs/{ref}", "deleted": True}

    def delete_branch(self, repository, branch, mutate=True):
        """Delete a branch reference."""
        branch = str(branch).removeprefix("refs/heads/")
        if not branch:
            raise ValueError("Git branch is required")
        return self.delete_ref(repository, f"refs/heads/{branch}", mutate=mutate)

    def tags(self, repository):
        """List repository tags."""
        return self._all(f"{self._repo(repository)}/tags", params={"per_page": 100})
