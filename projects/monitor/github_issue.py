# file: projects/monitor/github_issue.py

"""Monitor helpers for tracking GitHub issue closures."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import requests

from gway import gw

API_ROOT = "https://api.github.com"


def _now_iso() -> str:
    """Return the current time as an ISO-8601 string (seconds precision)."""

    return datetime.now().isoformat(timespec="seconds")


def _normalize_issue(issue: int | str | None) -> int:
    """Return the numeric issue identifier from user input."""

    if issue is None:
        raise ValueError("issue number is required")
    if isinstance(issue, int):
        if issue <= 0:
            raise ValueError("issue number must be positive")
        return issue
    cleaned = str(issue).strip().lstrip("#")
    if not cleaned.isdigit():
        raise ValueError(f"invalid issue number: {issue}")
    number = int(cleaned)
    if number <= 0:
        raise ValueError("issue number must be positive")
    return number


def _github_headers(token: str | None) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "gway-monitor",
    }
    if token:
        headers["Authorization"] = f"token {token}"
    return headers


def _fetch_issue(
    repo: str,
    issue: int,
    *,
    session: Any | None = None,
    token: str | None = None,
    timeout: float = 10.0,
) -> tuple[dict[str, Any] | None, str | None]:
    """Return ``(payload, error)`` from the GitHub API."""

    auth_token = token if token is not None else gw.hub.get_token(default=None)
    headers = _github_headers(auth_token)
    url = f"{API_ROOT}/repos/{repo}/issues/{issue}"
    getter = session.get if session is not None else requests.get
    try:
        response = getter(url, headers=headers, timeout=timeout)
    except requests.RequestException as exc:  # pragma: no cover - network failure
        return None, f"GitHub request failed: {exc}"
    except Exception as exc:  # pragma: no cover - unexpected failure
        return None, f"GitHub request error: {exc}"

    if response.status_code != 200:
        message = (response.text or "").strip() or getattr(response, "reason", "") or "unknown"
        if response.status_code == 404:
            message = f"Issue #{issue} not found in {repo}"
        else:
            message = f"GitHub API error {response.status_code}: {message}"
        return None, message

    try:
        return response.json(), None
    except ValueError:
        return None, "Invalid JSON response from GitHub"


def _issue_state(payload: dict[str, Any], repo: str, checked_at: str) -> dict[str, Any]:
    """Extract relevant fields from the GitHub payload."""

    closed = (payload.get("state") == "closed")
    user = payload.get("user") or {}
    closed_by = payload.get("closed_by") or {}
    labels = [lbl.get("name") for lbl in payload.get("labels") or [] if isinstance(lbl, dict)]
    return {
        "repo": repo,
        "number": payload.get("number"),
        "title": payload.get("title"),
        "state": payload.get("state"),
        "closed": closed,
        "closed_at": payload.get("closed_at"),
        "updated_at": payload.get("updated_at"),
        "url": payload.get("html_url"),
        "user": user.get("login"),
        "closed_by": closed_by.get("login") if closed else None,
        "labels": [label for label in labels if label],
        "checked_at": checked_at,
    }


def monitor_github_issue(
    issue: int | str | None = None,
    *,
    repo: str = "arthexis/gway",
    session: Any | None = None,
    token: str | None = None,
    timeout: float = 10.0,
) -> dict[str, Any]:
    """Update monitor state for a GitHub issue and report its closure."""

    issue_number = _normalize_issue(issue)
    checked_at = _now_iso()
    payload, error = _fetch_issue(repo, issue_number, session=session, token=token, timeout=timeout)

    state = gw.monitor.get_state("github_issue")
    issues = dict(state.get("issues") or {})
    issue_key = str(issue_number)

    update = {
        "issues": issues,
        "last_monitor_check": checked_at,
        "last_issue_checked": issue_key,
    }

    if error:
        issues[issue_key] = {
            "repo": repo,
            "number": issue_number,
            "error": error,
            "closed": None,
            "checked_at": checked_at,
        }
        update["last_error"] = error
        update["last_closed_issue"] = None
        update["last_closed_at"] = None
        gw.monitor.set_states("github_issue", update)
        return {
            "issue": issue_number,
            "repo": repo,
            "closed": None,
            "ok": False,
            "error": error,
        }

    issue_state = _issue_state(payload, repo, checked_at)
    issues[issue_key] = issue_state

    update["last_error"] = None
    if issue_state["closed"]:
        update["last_closed_issue"] = issue_key
        update["last_closed_at"] = issue_state.get("closed_at")
    else:
        update["last_closed_issue"] = None
        update["last_closed_at"] = None

    gw.monitor.set_states("github_issue", update)

    return {
        "issue": issue_number,
        "repo": repo,
        "title": issue_state.get("title"),
        "url": issue_state.get("url"),
        "state": issue_state.get("state"),
        "closed": issue_state["closed"],
        "ok": issue_state["closed"],
    }


def render_github_issue(issue: int | str | None = None) -> str:
    """Return an HTML fragment showing the state of the requested issue."""

    issue_number = _normalize_issue(issue)
    state = gw.monitor.get_state("github_issue")
    data = (state.get("issues") or {}).get(str(issue_number))
    if not data:
        return f"<div>No data for issue #{issue_number}.</div>"
    status = "closed" if data.get("closed") else "open"
    title = data.get("title") or "(no title)"
    url = data.get("url")
    repo = data.get("repo")
    checked = data.get("checked_at") or "-"
    closed_at = data.get("closed_at") or "-"
    parts = [
        f"<div class='github-issue'><strong>{repo}#{issue_number}</strong>: {title}</div>",
        f"<div>Status: <b>{status}</b></div>",
        f"<div>Last checked: {checked}</div>",
    ]
    if url:
        parts.append(f"<div><a href='{url}'>View on GitHub</a></div>")
    if data.get("closed"):
        parts.append(f"<div>Closed at: {closed_at}</div>")
    return "".join(parts)

