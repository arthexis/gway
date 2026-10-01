"""Shared GitHub capability helpers used by domain operation mixins."""

from __future__ import annotations

from urllib.parse import quote

from .github import Client


def segment(value):
    """Encode one GitHub REST path segment."""
    return quote(str(value), safe="")


class BaseOperations:
    """Shared transport, repository-root, and pagination helpers."""

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
        return "/repos/" + "/".join(segment(part) for part in repository.split("/"))

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
