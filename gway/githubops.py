"""Read-only GitHub repository/source operations."""

from __future__ import annotations

from urllib.parse import quote

from .github import Client


def _segment(value):
    return quote(str(value), safe="")


class Controller:
    """GitHub repository inspection operations."""

    def __init__(self, gateway, client=None):
        self.gateway = gateway
        self._client = client

    def _github(self):
        if self._client is not None:
            return self._client
        with self.gateway.topics("github"):
            token = self.gateway.resolve("[token]", default=None)
            api_url = self.gateway.resolve(
                "[api_url]",
                default="https://api.github.com/",
            )
        return Client(token, api_url=api_url)

    def _repo(self, repository):
        repository = str(repository).strip("/")
        if repository.count("/") != 1:
            raise ValueError("repository must be in owner/name form")
        return "/repos/" + "/".join(_segment(part) for part in repository.split("/"))

    def _all(self, path, *, params=None):
        result = []
        for page in self._github().pages(path, params=params):
            if not isinstance(page.data, list):
                raise TypeError("GitHub collection response must be a list")
            result.extend(page.data)
        return result

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
            "GET",
            f"{self._repo(repository)}/branches/{_segment(branch)}",
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
            "GET",
            f"{self._repo(repository)}/commits/{_segment(commit)}",
        ).data

    def file(self, repository, path, ref=None):
        """Return repository file or directory metadata/content."""
        params = {"ref": ref} if ref is not None else None
        encoded = quote(str(path).strip("/"), safe="/")
        return self._github().request(
            "GET",
            f"{self._repo(repository)}/contents/{encoded}",
            params=params,
        ).data

    def tree(self, repository, tree, recursive=False):
        """Return a Git tree."""
        params = {"recursive": "1"} if recursive else None
        return self._github().request(
            "GET",
            f"{self._repo(repository)}/git/trees/{_segment(tree)}",
            params=params,
        ).data

    def ref(self, repository, ref):
        """Return one Git reference."""
        encoded = quote(str(ref).removeprefix("refs/"), safe="/")
        return self._github().request(
            "GET",
            f"{self._repo(repository)}/git/ref/{encoded}",
        ).data

    def refs(self, repository, namespace=None):
        """List Git references, optionally below a namespace."""
        suffix = ""
        if namespace:
            suffix = "/" + quote(str(namespace).removeprefix("refs/"), safe="/")
        return self._all(f"{self._repo(repository)}/git/matching-refs{suffix}")

    def tags(self, repository):
        """List repository tags."""
        return self._all(
            f"{self._repo(repository)}/tags",
            params={"per_page": 100},
        )

    def pulls(self, repository, state="open"):
        """List pull requests."""
        return self._all(f"{self._repo(repository)}/pulls", params={"state": state, "per_page": 100})

    def pull(self, repository, number):
        """Return one pull request."""
        return self._github().request("GET", f"{self._repo(repository)}/pulls/{int(number)}").data

    def issues(self, repository, state="open"):
        """List issue records, including pull requests as GitHub returns them."""
        return self._all(f"{self._repo(repository)}/issues", params={"state": state, "per_page": 100})

    def issue(self, repository, number):
        """Return one issue record."""
        return self._github().request("GET", f"{self._repo(repository)}/issues/{int(number)}").data

    def comments(self, repository, number):
        """List conversation comments for an issue or pull request."""
        return self._all(f"{self._repo(repository)}/issues/{int(number)}/comments", params={"per_page": 100})

    def reviews(self, repository, number):
        """List submitted pull-request reviews."""
        return self._all(f"{self._repo(repository)}/pulls/{int(number)}/reviews", params={"per_page": 100})

    def review_comments(self, repository, number):
        """List inline pull-request review comments."""
        return self._all(f"{self._repo(repository)}/pulls/{int(number)}/comments", params={"per_page": 100})

    def review_threads(self, repository, number, unresolved=False):
        """List pull-request review threads, optionally only unresolved threads."""
        owner, name = str(repository).strip("/").split("/", 1)
        query = """
        query($owner: String!, $name: String!, $number: Int!, $after: String) {
          repository(owner: $owner, name: $name) {
            pullRequest(number: $number) {
              reviewThreads(first: 100, after: $after) {
                nodes {
                  id
                  isResolved
                  isOutdated
                  path
                  line
                  comments(first: 100) {
                    nodes { id body url author { login } createdAt }
                  }
                }
                pageInfo { hasNextPage endCursor }
              }
            }
          }
        }
        """
        variables = {"owner": owner, "name": name, "number": int(number), "after": None}
        threads = []
        while True:
            payload = self._github().graphql(query, variables).data
            if payload.get("errors"):
                raise RuntimeError(f"GitHub GraphQL error: {payload['errors']}")
            connection = payload["data"]["repository"]["pullRequest"]["reviewThreads"]
            threads.extend(connection["nodes"])
            page = connection["pageInfo"]
            if not page["hasNextPage"]:
                break
            variables["after"] = page["endCursor"]
        if unresolved:
            threads = [thread for thread in threads if not thread["isResolved"]]
        return threads
