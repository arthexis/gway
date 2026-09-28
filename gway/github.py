"""Thin GitHub REST client built on GWAY's shared HTTP transport."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin

from gway.http import HTTPResponse, request as http_request


API_URL = "https://api.github.com/"
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
        self._transport = transport

    def _headers(self, headers=None):
        result = {
            "Accept": ACCEPT,
            "Authorization": f"Bearer {self._token}",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": "gway-github/1",
        }
        result.update(headers or {})
        return result

    def request(self, method, path, *, params=None, json=None, headers=None):
        """Perform one GitHub REST request."""
        url = path if str(path).startswith(("http://", "https://")) else urljoin(
            self.api_url, str(path).lstrip("/")
        )
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

    def pages(self, path, *, params=None):
        """Yield each page from a GitHub collection response."""
        response = self.request("GET", path, params=params)
        while True:
            yield response
            if not response.next_url:
                return
            response = self.request("GET", response.next_url)
