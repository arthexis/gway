"""Git/GitHub source resolution and cache materialization."""

from dataclasses import dataclass
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from urllib.parse import urlsplit
import uuid

from ..cache import Cache
from .source import fingerprint


_GITHUB_SHORT = re.compile(
    r"^(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?$"
)
_GITHUB_SCP = re.compile(
    r"^git@github\.com:(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?$"
)


@dataclass(frozen=True)
class GitArtifact:
    """One immutable Git tree materialized from a cached repository mirror."""

    source: str
    requested_ref: str | None
    resolved_revision: str
    path: Path

    def __post_init__(self):
        object.__setattr__(self, "path", Path(self.path))


def normalize_source(source):
    """Return a canonical Git source spelling or raise ValueError."""
    source = str(source).strip()
    if not source:
        raise ValueError("Git source cannot be empty")

    match = _GITHUB_SHORT.fullmatch(source)
    if match:
        return (
            "https://github.com/"
            f"{match.group('owner')}/{match.group('repo')}.git"
        )

    match = _GITHUB_SCP.fullmatch(source)
    if match:
        return (
            "git@github.com:"
            f"{match.group('owner')}/{match.group('repo')}.git"
        )

    parsed = urlsplit(source)
    if parsed.scheme in {"http", "https"} and parsed.hostname in {
        "github.com",
        "www.github.com",
    }:
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) == 2:
            owner, repo = parts
            repo = repo[:-4] if repo.endswith(".git") else repo
            if (
                _GITHUB_SHORT.fullmatch(f"{owner}/{repo}")
                and not parsed.query
                and not parsed.fragment
            ):
                return f"https://github.com/{owner}/{repo}.git"

    if parsed.scheme in {"git", "ssh", "file"}:
        return source

    if parsed.scheme in {"http", "https"} and parsed.path.endswith(".git"):
        return source

    raise ValueError(f"Unsupported Git source: {source}")


def is_git_source(source):
    """Return whether a string denotes Git/GitHub source intent."""
    try:
        normalize_source(source)
    except (TypeError, ValueError):
        return False
    return True


def _run_git(arguments, *, cwd=None):
    try:
        result = subprocess.run(
            ["git", *map(str, arguments)],
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "Git installation sources require the git executable"
        ) from exc

    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(
            f"Git command failed{': ' + detail if detail else ''}"
        )
    return result.stdout.strip()


def _mirror(cache, source):
    entry = cache.entry("git", source)
    mirror = entry / "mirror.git"

    if mirror.is_dir():
        _run_git(
            [
                f"--git-dir={mirror}",
                "remote",
                "set-url",
                "origin",
                source,
            ]
        )
        _run_git(
            [
                f"--git-dir={mirror}",
                "remote",
                "update",
                "--prune",
            ]
        )
        return entry, mirror

    if mirror.exists():
        raise RuntimeError(f"Git cache mirror is not a directory: {mirror}")

    temporary = entry / f".mirror-{uuid.uuid4().hex}.git"
    try:
        _run_git(["clone", "--mirror", source, temporary])
        os.replace(temporary, mirror)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return entry, mirror


def _resolve_revision(mirror, ref):
    if ref is None:
        candidate = "HEAD"
        return _run_git(
            [
                f"--git-dir={mirror}",
                "rev-parse",
                "--verify",
                f"{candidate}^{{commit}}",
            ]
        )

    candidates = [ref]
    if not ref.startswith("refs/"):
        candidates.extend(
            [
                f"refs/heads/{ref}",
                f"refs/tags/{ref}",
            ]
        )

    for candidate in dict.fromkeys(candidates):
        try:
            return _run_git(
                [
                    f"--git-dir={mirror}",
                    "rev-parse",
                    "--verify",
                    f"{candidate}^{{commit}}",
                ]
            )
        except RuntimeError:
            continue

    raise ValueError(f"Unable to resolve Git ref {ref!r}")


def _valid_snapshot(snapshot, metadata):
    if not snapshot.is_dir() or not isinstance(metadata, dict):
        return False
    expected = metadata.get("fingerprint")
    if not isinstance(expected, str):
        return False
    try:
        return fingerprint(snapshot) == expected
    except (OSError, ValueError):
        return False


def _snapshot(cache, entry, mirror, source, revision):
    snapshots = entry / "snapshots"
    snapshots.mkdir(parents=True, exist_ok=True)
    snapshot = snapshots / revision
    metadata_path = snapshots / f"{revision}.json"
    metadata = cache.read_json(metadata_path)

    if _valid_snapshot(snapshot, metadata):
        return snapshot

    if snapshot.exists():
        shutil.rmtree(snapshot)

    stage = Path(
        tempfile.mkdtemp(
            prefix=f".{revision}.stage-",
            dir=snapshots,
        )
    )
    try:
        _run_git(
            [
                "clone",
                "--no-checkout",
                "--shared",
                mirror,
                stage,
            ]
        )
        _run_git(
            [
                "-C",
                stage,
                "checkout",
                "--detach",
                "--force",
                revision,
            ]
        )
        git_dir = stage / ".git"
        if git_dir.is_dir():
            shutil.rmtree(git_dir)
        elif git_dir.exists():
            git_dir.unlink()

        tree_fingerprint = fingerprint(stage)
        os.replace(stage, snapshot)
        cache.write_json(
            metadata_path,
            {
                "source": source,
                "resolved_revision": revision,
                "fingerprint": tree_fingerprint,
            },
        )
    finally:
        if stage.exists():
            shutil.rmtree(stage)

    return snapshot


def materialize(source, *, ref=None, cache=None):
    """Fetch a Git source and materialize one immutable commit tree."""
    source = normalize_source(source)
    cache = Cache() if cache is None else cache
    if not isinstance(cache, Cache):
        cache = Cache(cache)

    entry, mirror = _mirror(cache, source)
    revision = _resolve_revision(mirror, ref)
    snapshot = _snapshot(
        cache,
        entry,
        mirror,
        source,
        revision,
    )
    return GitArtifact(
        source=source,
        requested_ref=ref,
        resolved_revision=revision,
        path=snapshot,
    )
