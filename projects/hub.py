# file: projects/hub.py

"""Utilities for interacting with GitHub and the local git repository."""

from gway import gw


def get_token(default=None):
    """Return the first configured GitHub token found."""
    return gw.resolve("[GITHUB_TOKEN]", "[GH_TOKEN]", "[REPO_TOKEN]", default=default)


def create_issue(title: str, body: str, *, repo: str = "arthexis/gway") -> str:
    """Create an issue in the given repository and return its URL."""
    import requests

    token = get_token()
    if not token:
        raise RuntimeError("GitHub token not configured")

    url = f"https://api.github.com/repos/{repo}/issues"
    headers = {
        "Authorization": f"token {token}",
        "User-Agent": "gway-feedback",
        "Accept": "application/vnd.github+json",
    }
    resp = requests.post(url, json={"title": title, "body": body}, headers=headers, timeout=10)
    if resp.status_code != 201:
        raise RuntimeError(f"GitHub API error: {resp.status_code} {resp.text}")
    data = resp.json()
    return data.get("html_url", "")


def commit(length: int = 6) -> str:
    """Return the current git commit hash (optionally truncated)."""
    import subprocess

    try:
        full = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
        return full[-length:] if length else full
    except Exception:
        return "unknown"


def get_build(length: int = 6) -> str:
    """Return the build hash stored in the BUILD file."""
    from pathlib import Path

    build_path = Path("BUILD")
    if build_path.exists():
        commit_hash = build_path.read_text().strip()
        return commit_hash[-length:] if length else commit_hash
    gw.warning("BUILD file not found.")
    return "unknown"


def changes(*, files=None, staged=False, context=3, max_bytes=200_000, clip=False):
    """Return a unified diff of recent textual changes in the git repository."""
    import subprocess

    cmd = ["git", "diff", f"--unified={context}"]
    if staged:
        cmd.insert(2, "--staged")
    if files:
        if isinstance(files, str):
            files = [files]
        cmd += list(files)

    try:
        diff = subprocess.check_output(cmd, encoding="utf-8", errors="replace")
    except subprocess.CalledProcessError as e:
        return f"[ERROR] Unable to get git diff: {e}"
    except FileNotFoundError:
        return "[ERROR] git command not found. Are you in a git repo?"

    filtered = []
    skip = False
    for line in diff.splitlines(keepends=True):
        if line.startswith("Binary files "):
            continue
        if line.startswith("diff --git"):
            skip = False
        if "GIT binary patch" in line:
            skip = True
        if skip:
            continue
        filtered.append(line)

    result = "".join(filtered)
    if len(result) > max_bytes:
        result = result[:max_bytes] + f"\n[...Diff truncated at {max_bytes} bytes...]"

    if clip:
        gw.clip.copy(result)
    if not gw.silent:
        return result or "[No changes detected]"

