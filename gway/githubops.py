"""Read-only GitHub repository/source operations."""

from __future__ import annotations

from urllib.parse import quote
import base64

from .github import Client, GitHubError


def _segment(value):
    return quote(str(value), safe="")


WRITE_OPERATIONS = frozenset({
    "set_variable",
    "delete_variable",
    "set_secret",
    "delete_secret",
    "create_issue",
    "update_issue",
    "close_issue",
    "reopen_issue",
    "comment_issue",
    "create_pull",
    "update_pull",
    "close_pull",
    "reopen_pull",
    "reply_review_comment",
    "add_labels",
    "remove_label",
    "ready_pull",
    "draft_pull",
    "merge_pull",
    "dispatch_workflow",
    "dispatch_repository",
    "create_release",
    "update_release",
    "create_ref",
    "create_branch",
    "delete_ref",
    "delete_branch",
    "create_file",
    "update_file",
    "delete_file",
})


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

    def _all_enveloped(self, path, key, *, params=None):
        result = []
        response = self._github().request("GET", path, params=params)
        while True:
            data = response.data
            if not isinstance(data, dict) or not isinstance(data.get(key), list):
                raise TypeError(f"GitHub collection response must contain a {key} list")
            result.extend(data[key])
            next_url = getattr(response, "next_url", None)
            if not next_url:
                return result
            response = self._github().request("GET", next_url)

    def repository(self, repository):
        """Return GitHub repository metadata."""
        return self._github().request("GET", self._repo(repository)).data

    def status(self, repository):
        """Return compact GitHub repository/source-control status."""
        repo = self.repository(repository)
        branch = repo.get("default_branch") if isinstance(repo, dict) else None
        return {
            "repository": (
                repo.get("full_name") if isinstance(repo, dict) else repository
            ),
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

    def create_file(
        self, repository, path, content, message, branch=None, mutate=True
    ):
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
            "PUT",
            f"{self._repo(repository)}/contents/{encoded}",
            json=payload,
        ).data

    def update_file(
        self,
        repository,
        path,
        content,
        message,
        sha,
        branch=None,
        mutate=True,
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
            "PUT",
            f"{self._repo(repository)}/contents/{encoded}",
            json=payload,
        ).data

    def delete_file(
        self, repository, path, message, sha, branch=None, mutate=True
    ):
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
            "DELETE",
            f"{self._repo(repository)}/contents/{encoded}",
            json=payload,
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
            "POST",
            f"{self._repo(repository)}/git/refs",
            json={"ref": full_ref, "sha": sha},
        ).data

    def create_branch(self, repository, branch, sha, mutate=True):
        """Create a branch at an explicit commit SHA."""
        branch = str(branch).removeprefix("refs/heads/")
        if not branch:
            raise ValueError("Git branch is required")
        return self.create_ref(
            repository, f"refs/heads/{branch}", sha, mutate=mutate
        )

    def delete_ref(self, repository, ref, mutate=True):
        """Delete an explicit Git reference."""
        if not mutate:
            raise PermissionError("GitHub reference mutation is disabled")
        ref = str(ref).removeprefix("refs/")
        if not ref:
            raise ValueError("Git reference is required")
        self._github().request(
            "DELETE",
            f"{self._repo(repository)}/git/refs/{quote(ref, safe='/')}",
        )
        return {
            "repository": str(repository),
            "ref": f"refs/{ref}",
            "deleted": True,
        }

    def delete_branch(self, repository, branch, mutate=True):
        """Delete a branch reference."""
        branch = str(branch).removeprefix("refs/heads/")
        if not branch:
            raise ValueError("Git branch is required")
        return self.delete_ref(
            repository, f"refs/heads/{branch}", mutate=mutate
        )

    def tags(self, repository):
        """List repository tags."""
        return self._all(
            f"{self._repo(repository)}/tags",
            params={"per_page": 100},
        )

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
            "PATCH",
            f"{self._repo(repository)}/pulls/{int(number)}",
            json=payload,
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
        if not str(sha):
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
            "PATCH",
            f"{self._repo(repository)}/issues/{int(number)}",
            json=payload,
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

    def reply_review_comment(
        self, repository, number, comment, body, mutate=True
    ):
        """Reply to an inline pull-request review comment."""
        if not mutate:
            raise PermissionError("GitHub pull request mutation is disabled")
        return self._github().request(
            "POST",
            f"{self._repo(repository)}/pulls/{int(number)}/comments/{int(comment)}/replies",
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
            f"{self._repo(repository)}/issues/{int(number)}/labels/{_segment(label)}",
        ).data

    def reviews(self, repository, number):
        """List submitted pull-request reviews."""
        return self._all(
            f"{self._repo(repository)}/pulls/{int(number)}/reviews",
            params={"per_page": 100},
        )

    def review_comments(self, repository, number):
        """List inline pull-request review comments."""
        return self._all(
            f"{self._repo(repository)}/pulls/{int(number)}/comments",
            params={"per_page": 100},
        )

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

    def runs(self, repository, workflow=None, branch=None, status=None):
        """List GitHub Actions runs, optionally filtered by workflow or branch."""
        root = self._repo(repository)
        path = f"{root}/actions/runs"
        if workflow is not None:
            path = f"{root}/actions/workflows/{_segment(workflow)}/runs"
        params = {"per_page": 100}
        if branch is not None:
            params["branch"] = branch
        if status is not None:
            params["status"] = status
        return self._all_enveloped(path, "workflow_runs", params=params)

    def run(self, repository, run):
        """Return one GitHub Actions workflow run."""
        return self._github().request(
            "GET",
            f"{self._repo(repository)}/actions/runs/{int(run)}",
        ).data

    def jobs(self, repository, run):
        """List jobs belonging to a GitHub Actions workflow run."""
        return self._all_enveloped(
            f"{self._repo(repository)}/actions/runs/{int(run)}/jobs",
            "jobs",
            params={"per_page": 100},
        )

    def job(self, repository, job):
        """Return one GitHub Actions job."""
        return self._github().request(
            "GET",
            f"{self._repo(repository)}/actions/jobs/{int(job)}",
        ).data

    def checks(self, repository, ref):
        """List check runs for a commit or Git ref."""
        return self._all_enveloped(
            f"{self._repo(repository)}/commits/{_segment(ref)}/check-runs",
            "check_runs",
            params={"per_page": 100},
        )

    def check(self, repository, check):
        """Return one check run."""
        return self._github().request(
            "GET",
            f"{self._repo(repository)}/check-runs/{int(check)}",
        ).data

    def job_logs(self, repository, job):
        """Return the downloadable log response for one Actions job."""
        response = self._github().download_redirect(
            f"{self._repo(repository)}/actions/jobs/{int(job)}/logs"
        )
        return {
            "status": response.status,
            "content": response.data,
            "content_type": response.headers.get("content-type"),
        }

    def workflows(self, repository):
        """List GitHub Actions workflow definitions."""
        return self._all_enveloped(
            f"{self._repo(repository)}/actions/workflows",
            "workflows",
            params={"per_page": 100},
        )

    def workflow(self, repository, workflow):
        """Return one workflow definition by numeric ID or file name."""
        return self._github().request(
            "GET",
            f"{self._repo(repository)}/actions/workflows/{_segment(workflow)}",
        ).data

    def dispatch_workflow(
        self, repository, workflow, ref, inputs=None, mutate=True
    ):
        """Dispatch a GitHub Actions workflow at an explicit ref."""
        if not mutate:
            raise PermissionError("GitHub workflow mutation is disabled")
        payload = {"ref": str(ref)}
        if inputs is not None:
            if not isinstance(inputs, dict):
                raise TypeError("workflow inputs must be a mapping")
            payload["inputs"] = dict(inputs)
        self._github().request(
            "POST",
            f"{self._repo(repository)}/actions/workflows/{_segment(workflow)}/dispatches",
            json=payload,
        )
        return {
            "repository": str(repository),
            "workflow": str(workflow),
            "ref": str(ref),
            "dispatched": True,
        }

    def dispatch_repository(
        self, repository, event, payload=None, mutate=True
    ):
        """Dispatch a repository event with an optional client payload."""
        if not mutate:
            raise PermissionError("GitHub repository mutation is disabled")
        if not str(event):
            raise ValueError("repository dispatch event is required")
        body = {"event_type": str(event)}
        if payload is not None:
            if not isinstance(payload, dict):
                raise TypeError("repository dispatch payload must be a mapping")
            body["client_payload"] = dict(payload)
        self._github().request(
            "POST",
            f"{self._repo(repository)}/dispatches",
            json=body,
        )
        return {
            "repository": str(repository),
            "event": str(event),
            "dispatched": True,
        }

    def releases(self, repository):
        """List repository releases."""
        return self._all(
            f"{self._repo(repository)}/releases",
            params={"per_page": 100},
        )

    def release(self, repository, release):
        """Return one repository release by numeric ID."""
        return self._github().request(
            "GET",
            f"{self._repo(repository)}/releases/{int(release)}",
        ).data

    def release_tag(self, repository, tag):
        """Return one repository release by tag."""
        return self._github().request(
            "GET",
            f"{self._repo(repository)}/releases/tags/{_segment(tag)}",
        ).data

    def latest_release(self, repository):
        """Return the repository's latest published release."""
        return self._github().request(
            "GET",
            f"{self._repo(repository)}/releases/latest",
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
            "POST",
            f"{self._repo(repository)}/releases",
            json=payload,
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

    def variables(self, repository):
        """List GitHub Actions repository variables and their visible values."""
        return self._all_enveloped(
            f"{self._repo(repository)}/actions/variables",
            "variables",
            params={"per_page": 100},
        )

    def variable(self, repository, name):
        """Return one GitHub Actions repository variable."""
        return self._github().request(
            "GET",
            f"{self._repo(repository)}/actions/variables/{_segment(name)}",
        ).data

    def secrets(self, repository):
        """List Actions secret metadata; secret values are never available."""
        return self._all_enveloped(
            f"{self._repo(repository)}/actions/secrets",
            "secrets",
            params={"per_page": 100},
        )

    def secret(self, repository, name):
        """Return metadata for one Actions secret, never its value."""
        return self._github().request(
            "GET",
            f"{self._repo(repository)}/actions/secrets/{_segment(name)}",
        ).data

    def set_variable(self, repository, name, value, mutate=True):
        """Converge a GitHub Actions repository variable to the requested value."""
        if not mutate:
            raise PermissionError("GitHub variable mutation is disabled")
        root = f"{self._repo(repository)}/actions/variables"
        path = f"{root}/{_segment(name)}"
        payload = {"name": str(name), "value": str(value)}
        try:
            self._github().request("GET", path)
        except GitHubError as error:
            if error.status != 404:
                raise
            try:
                self._github().request("POST", root, json=payload)
                return {"name": str(name), "value": str(value), "created": True}
            except GitHubError as create_error:
                if create_error.status not in {409, 422}:
                    raise
                self._github().request("PATCH", path, json=payload)
                return {"name": str(name), "value": str(value), "created": False}
        try:
            self._github().request("PATCH", path, json=payload)
            return {"name": str(name), "value": str(value), "created": False}
        except GitHubError as update_error:
            if update_error.status != 404:
                raise
            self._github().request("POST", root, json=payload)
            return {"name": str(name), "value": str(value), "created": True}

    def delete_variable(self, repository, name, mutate=True):
        """Delete a GitHub Actions repository variable."""
        if not mutate:
            raise PermissionError("GitHub variable mutation is disabled")
        self._github().request(
            "DELETE",
            f"{self._repo(repository)}/actions/variables/{_segment(name)}",
        )
        return {"name": str(name), "deleted": True}

    def secret_key(self, repository):
        """Return the Actions public key used to encrypt repository secrets."""
        return self._github().request(
            "GET",
            f"{self._repo(repository)}/actions/secrets/public-key",
        ).data

    @staticmethod
    def _encrypt_secret(public_key, value):
        try:
            from nacl import encoding, public
        except ImportError as error:
            raise RuntimeError(
                "GitHub secret writes require PyNaCl"
            ) from error
        key = public.PublicKey(str(public_key), encoding.Base64Encoder())
        box = public.SealedBox(key)
        encrypted = box.encrypt(str(value).encode("utf-8"))
        return base64.b64encode(encrypted).decode("ascii")

    def set_secret(self, repository, name, value, mutate=True):
        """Encrypt and set a GitHub Actions repository secret."""
        if not mutate:
            raise PermissionError("GitHub secret mutation is disabled")
        key = self.secret_key(repository)
        if not isinstance(key, dict) or not key.get("key") or not key.get("key_id"):
            raise ValueError("GitHub Actions secret public key response is incomplete")
        encrypted = self._encrypt_secret(key["key"], value)
        self._github().request(
            "PUT",
            f"{self._repo(repository)}/actions/secrets/{_segment(name)}",
            json={"encrypted_value": encrypted, "key_id": key["key_id"]},
        )
        return {"name": str(name), "updated": True}

    def delete_secret(self, repository, name, mutate=True):
        """Delete a GitHub Actions repository secret."""
        if not mutate:
            raise PermissionError("GitHub secret mutation is disabled")
        self._github().request(
            "DELETE",
            f"{self._repo(repository)}/actions/secrets/{_segment(name)}",
        )
        return {"name": str(name), "deleted": True}
