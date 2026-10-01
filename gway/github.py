"""Compatibility imports for the sampler-owned GitHub client.

GitHub is a maintained sampler capability. New implementation code belongs under
``sampler/github``; this module remains only for existing Python imports.
"""

from .sampler import load

_github = load("github")

Client = _github.Client
GitHubError = _github.GitHubError
GitHubResponse = _github.GitHubResponse
RateLimit = _github.RateLimit

__all__ = ["Client", "GitHubError", "GitHubResponse", "RateLimit"]
