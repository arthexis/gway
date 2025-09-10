# file: projects/gist.py

"""Publish gateway results to a GitHub gist."""

from gway import gw


def publish(*, description: str = "GWAY results", public: bool = False, filename: str = "results.json") -> str:
    """Create a GitHub gist with the current ``gw.results``.

    Parameters
    ----------
    description: str
        Optional description for the created gist.
    public: bool
        Whether the gist should be public. Defaults to ``False`` (secret gist).
    filename: str
        Name of the file inside the gist.

    Returns
    -------
    str
        URL of the created gist.
    """
    import json
    import requests

    data = gw.results.get_results()
    if not data:
        raise RuntimeError("No results available to publish")

    token = gw.hub.get_token()
    if not token:
        raise RuntimeError("GitHub token not configured")

    payload = {
        "description": description,
        "public": public,
        "files": {filename: {"content": json.dumps(data, indent=2, default=str)}},
    }
    headers = {
        "Authorization": f"token {token}",
        "User-Agent": "gway-gist",
        "Accept": "application/vnd.github+json",
    }
    resp = requests.post("https://api.github.com/gists", json=payload, headers=headers, timeout=10)
    if resp.status_code != 201:
        raise RuntimeError(f"GitHub API error: {resp.status_code} {resp.text}")

    url = resp.json().get("html_url", "")
    gw.success(url)
    return url
