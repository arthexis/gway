"""Thin GitHub REST client built on GWAY's shared HTTP transport."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

from gway.http import HTTPResponse, request as http_request


API_URL = "https://api.github.com/"
GRAPHQL_URL = "https://api.github.com/graphql"
API_VERSION = "2022-11-28"
ACCEPT = "application/vnd.github+json"


class GitHubError(RuntimeError):
    """Raised when GitHub returns an unsuccessful API response."""

    def __init__(self, status, message, *, request_id=None):
        self.status = int(status)
        self.request_id = request_id
        detail = f"GitHub API returned HTTP {self.status}: {message}"
        if request_id:
            detail += f" (request {request_id})"
        super().__init__(detail)


@dataclass(frozen=True)
class RateLimit:
    """Rate-limit metadata returned by GitHub when available."""

    limit: int | None = None
    remaining: int | None = None
    reset: int | None = None
    resource: str | None = None


@dataclass(frozen=True)
class GitHubResponse:
    """Provider response plus GitHub pagination and rate-limit metadata."""

    data: object
    status: int
    headers: dict[str, str]
    next_url: str | None
    rate_limit: RateLimit


def _integer(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _links(value):
    links = {}
    for item in (value or "").split(","):
        parts = [part.strip() for part in item.split(";")]
        if len(parts) < 2 or not parts[0].startswith("<"):
            continue
        url = parts[0].strip("<>")
        for part in parts[1:]:
            if part.startswith('rel="') and part.endswith('"'):
                links[part[5:-1]] = url
    return links


class Client:
    """Authenticated GitHub REST transport.

    Args:
        token: Fine-grained PAT or GitHub App installation access token.
        api_url: GitHub REST API root, overridable for GitHub Enterprise/tests.
    """

    def __init__(self, token, api_url=API_URL, transport=None):
        if not token:
            raise ValueError("GitHub token is required")
        self._token = str(token)
        self.api_url = str(api_url).rstrip("/") + "/"
        self._origin = urlsplit(self.api_url)[:2]
        api_parts = urlsplit(self.api_url)
        if api_parts.path.rstrip("/").endswith("/api/v3"):
            graphql_path = api_parts.path.rstrip("/")[:-len("/api/v3")] + "/api/graphql"
            self.graphql_url = api_parts._replace(path=graphql_path, query="", fragment="").geturl()
        else:
            self.graphql_url = urljoin(self.api_url, "graphql")
        self._transport = transport

    def _headers(self, headers=None):
        result = {
            "Accept": ACCEPT,
            "Authorization": f"Bearer {self._token}",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": "gway-github/1",
        }
        custom = dict(headers or {})
        custom.pop("Authorization", None)
        result.update(custom)
        return result

    def request(self, method, path, *, params=None, json=None, headers=None):
        """Perform one GitHub REST request."""
        if str(path).startswith(("http://", "https://")):
            url = str(path)
            if urlsplit(url)[:2] != self._origin:
                raise ValueError("GitHub request URL must remain on the configured API origin")
        else:
            url = urljoin(self.api_url, str(path).lstrip("/"))
        response = http_request(
            method,
            url,
            headers=self._headers(headers),
            params=params,
            json=json,
            follow_redirects=False,
            transport=self._transport,
        )
        return self._result(response)

    def download_redirect(self, path):
        """Fetch a GitHub download redirect without forwarding credentials."""
        if str(path).startswith(("http://", "https://")):
            raise ValueError("GitHub download path must remain on the configured API origin")
        url = urljoin(self.api_url, str(path).lstrip("/"))
        response = http_request(
            "GET",
            url,
            headers=self._headers(),
            follow_redirects=False,
            transport=self._transport,
        )
        if response.status not in {301, 302, 303, 307, 308}:
            return self._result(response)
        location = response.headers.get("location")
        if not location:
            raise GitHubError(
                response.status,
                "download redirect is missing Location",
                request_id=response.headers.get("x-github-request-id"),
            )
        redirected = http_request(
            "GET",
            location,
            follow_redirects=True,
            transport=self._transport,
        )
        if redirected.status >= 400:
            raise GitHubError(
                redirected.status,
                "download request failed",
                request_id=response.headers.get("x-github-request-id"),
            )
        return GitHubResponse(
            data=redirected.content,
            status=redirected.status,
            headers=redirected.headers,
            next_url=None,
            rate_limit=RateLimit(),
        )

    def _result(self, response: HTTPResponse):
        request_id = response.headers.get("x-github-request-id")
        if response.status >= 400:
            message = "request failed"
            try:
                payload = response.json()
                if isinstance(payload, dict):
                    message = str(payload.get("message") or message)
            except ValueError:
                if response.text:
                    message = response.text
            raise GitHubError(response.status, message, request_id=request_id)

        if not response.content:
            data = None
        else:
            try:
                data = response.json()
            except ValueError:
                data = response.text

        return GitHubResponse(
            data=data,
            status=response.status,
            headers=response.headers,
            next_url=_links(response.headers.get("link")).get("next"),
            rate_limit=RateLimit(
                limit=_integer(response.headers.get("x-ratelimit-limit")),
                remaining=_integer(response.headers.get("x-ratelimit-remaining")),
                reset=_integer(response.headers.get("x-ratelimit-reset")),
                resource=response.headers.get("x-ratelimit-resource"),
            ),
        )

    def graphql(self, query, variables=None):
        """Execute a GitHub GraphQL read query."""
        return self.request(
            "POST",
            self.graphql_url,
            json={"query": query, "variables": variables or {}},
        )

    def pages(self, path, *, params=None):
        """Yield each page from a GitHub collection response."""
        response = self.request("GET", path, params=params)
        while True:
            yield response
            if not response.next_url:
                return
            response = self.request("GET", response.next_url)
