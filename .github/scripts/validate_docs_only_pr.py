#!/usr/bin/env python3
"""Fail unless a PR changes documentation files only."""

from __future__ import annotations

import subprocess
import sys
from pathlib import PurePosixPath


DOC_EXTENSIONS = {".md", ".rst", ".txt"}


def changed_files(base_sha: str, head_sha: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base_sha}..{head_sha}"],
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def is_documentation(path: str) -> bool:
    candidate = PurePosixPath(path)
    if candidate.parts and candidate.parts[0] == "docs":
        return True
    return len(candidate.parts) == 1 and candidate.suffix.lower() in DOC_EXTENSIONS


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: validate_docs_only_pr.py BASE_SHA HEAD_SHA", file=sys.stderr)
        return 2

    files = changed_files(sys.argv[1], sys.argv[2])
    if not files:
        print("docs-only validation failed: PR has no changed files", file=sys.stderr)
        return 1

    invalid = [path for path in files if not is_documentation(path)]
    if invalid:
        print("docs-only validation failed; non-documentation changes detected:", file=sys.stderr)
        for path in invalid:
            print(f"  {path}", file=sys.stderr)
        return 1

    print("docs-only validation passed:")
    for path in files:
        print(f"  {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
