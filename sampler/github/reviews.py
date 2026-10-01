"""GitHub pull-request review operations."""

from __future__ import annotations


class ReviewOperations:
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

    def review_decision(self, repository, number):
        """Return GitHub's aggregate review decision for one pull request."""
        owner, name = str(repository).strip("/").split("/", 1)
        query = """
        query($owner: String!, $name: String!, $number: Int!) {
          repository(owner: $owner, name: $name) {
            pullRequest(number: $number) {
              reviewDecision
            }
          }
        }
        """
        payload = self._github().graphql(
            query,
            {"owner": owner, "name": name, "number": int(number)},
        ).data
        if payload.get("errors"):
            raise RuntimeError(f"GitHub GraphQL error: {payload['errors']}")
        pull = ((payload.get("data") or {}).get("repository") or {}).get("pullRequest")
        if pull is None:
            raise ValueError("GitHub pull request response is missing review decision")
        return pull.get("reviewDecision")

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
        variables = {
            "owner": owner,
            "name": name,
            "number": int(number),
            "after": None,
        }
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
