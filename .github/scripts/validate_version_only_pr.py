#!/usr/bin/env python3
"""Validate that a PR labeled version only advances Gway project.version."""

from __future__ import annotations

import re
import subprocess
import sys

EXPECTED_FILES = {"pyproject.toml"}
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
PROJECT_VERSION_RE = re.compile(
    r'(?m)^(version\s*=\s*)"([^"]+)"(\s*)$'
)


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True)


def read_at(ref: str, path: str) -> str:
    return git("show", f"{ref}:{path}")


def project_version(text: str) -> str:
    match = PROJECT_VERSION_RE.search(text)
    if not match:
        raise SystemExit("pyproject.toml must contain a simple quoted project version")
    return match.group(2)


def as_tuple(version: str) -> tuple[int, int, int]:
    if not VERSION_RE.fullmatch(version):
        raise SystemExit(f"version must be X.Y.Z, got {version!r}")
    return tuple(map(int, version.split(".")))


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: validate_version_only_pr.py BASE_SHA HEAD_SHA")
    base, head = sys.argv[1:]

    changed = {
        line for line in git("diff", "--name-only", base, head).splitlines() if line
    }
    if changed != EXPECTED_FILES:
        raise SystemExit(
            f"version PR must change exactly {sorted(EXPECTED_FILES)!r}; got {sorted(changed)!r}"
        )

    old_py = read_at(base, "pyproject.toml")
    new_py = read_at(head, "pyproject.toml")
    old_version = project_version(old_py)
    new_version = project_version(new_py)

    expected_py = PROJECT_VERSION_RE.sub(
        lambda m: f'{m.group(1)}"{new_version}"{m.group(3)}',
        old_py,
        count=1,
    )
    if new_py != expected_py:
        raise SystemExit("pyproject.toml contains changes beyond project.version")
    if as_tuple(new_version) <= as_tuple(old_version):
        raise SystemExit(f"version must advance: {old_version} -> {new_version}")

    print(f"version_only=valid {old_version}->{new_version}")


if __name__ == "__main__":
    main()
