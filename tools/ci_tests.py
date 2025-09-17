#!/usr/bin/env python3
"""CI test harness that enables optional suites only when touched."""

from __future__ import annotations

import argparse
import fnmatch
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Sequence

OPTIONAL_FLAG_PATTERNS: dict[str, list[str]] = {
    "audio": [
        "projects/audio.py",
        "tests/test_audio_record.py",
    ],
    "video": [
        "projects/video.py",
        "tests/test_video.py",
    ],
    "lcd": [
        "projects/lcd.py",
        "tests/test_lcd.py",
    ],
    "sensors": [
        "projects/sensor.py",
        "projects/pir.py",
        "tests/test_sensor_motion.py",
        "tests/test_sensor_proximity.py",
        "tests/test_pir_sense_motion.py",
    ],
}


def parse_flag_list(value: str | None) -> list[str]:
    """Return parsed list of flags from comma/space separated text."""

    if not value:
        return []
    result: list[str] = []
    for part in value.replace(",", " ").split():
        flag = part.strip()
        if flag:
            result.append(flag)
    return result


def _run_git(args: Sequence[str], cwd: Path) -> tuple[int, str]:
    """Return exit code and stdout for ``git`` command executed in ``cwd``."""

    proc = subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return proc.returncode, proc.stdout


def gather_changed_files(repo_root: Path, base: str | None) -> set[str]:
    """Return repository-relative paths that differ from ``base`` or worktree."""

    changed: set[str] = set()
    candidates: list[list[str]] = []
    if base and _ref_exists(repo_root, base):
        candidates.append(["diff", "--name-only", f"{base}...HEAD"])
        candidates.append(["diff", "--name-only", f"{base}..HEAD"])
    env_base = os.environ.get("GWAY_CI_BASE")
    if env_base and env_base != base and _ref_exists(repo_root, env_base):
        candidates.append(["diff", "--name-only", f"{env_base}...HEAD"])
        candidates.append(["diff", "--name-only", f"{env_base}..HEAD"])

    for args in candidates:
        code, stdout = _run_git(args, repo_root)
        if code != 0:
            continue
        lines = [line.strip() for line in stdout.splitlines() if line.strip()]
        if lines:
            changed.update(lines)
            break

    status_code, status_out = _run_git(["status", "--porcelain"], repo_root)
    if status_code == 0:
        for line in status_out.splitlines():
            if len(line) < 4:
                continue
            path = line[3:].strip()
            if path:
                changed.add(path)

    return {_normalize_path(repo_root, path) for path in changed if path}


def _ref_exists(repo_root: Path, ref: str) -> bool:
    code, _ = _run_git(["rev-parse", "--verify", ref], repo_root)
    return code == 0


def _normalize_path(repo_root: Path, path: str) -> str:
    """Normalize ``path`` to repository-relative POSIX representation."""

    try:
        candidate = Path(path)
    except Exception:
        return path.replace("\\", "/")

    if candidate.is_absolute():
        try:
            relative = candidate.relative_to(repo_root)
        except ValueError:
            return candidate.as_posix()
        return relative.as_posix()
    return candidate.as_posix()


def detect_optional_flags(changed: Iterable[str]) -> dict[str, list[str]]:
    """Return mapping of optional flags to triggering paths."""

    hits: dict[str, set[str]] = {}
    normalized_patterns = {
        flag: [_normalize_pattern(p) for p in patterns]
        for flag, patterns in OPTIONAL_FLAG_PATTERNS.items()
    }

    for path in changed:
        for flag, patterns in normalized_patterns.items():
            for pattern in patterns:
                if _matches(path, pattern):
                    hits.setdefault(flag, set()).add(path)
                    break

    return {flag: sorted(paths) for flag, paths in sorted(hits.items())}


def _normalize_pattern(pattern: str) -> str:
    return pattern.strip().replace("\\", "/")


def _matches(path: str, pattern: str) -> bool:
    if not pattern:
        return False
    if any(ch in pattern for ch in "*?[]"):
        return fnmatch.fnmatch(path, pattern)
    if pattern.endswith("/"):
        prefix = pattern.rstrip("/")
        return path == prefix or path.startswith(prefix + "/")
    return path == pattern


def _strip_manual_flags(args: list[str]) -> tuple[list[str], list[str]]:
    """Remove ``--flags`` options from ``args`` and return remaining + values."""

    cleaned: list[str] = []
    manual: list[str] = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--flags":
            if i + 1 < len(args):
                manual.extend(parse_flag_list(args[i + 1]))
                i += 2
            else:
                i += 1
            continue
        if arg.startswith("--flags="):
            manual.extend(parse_flag_list(arg.split("=", 1)[1]))
            i += 1
            continue
        cleaned.append(arg)
        i += 1
    return cleaned, manual


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base",
        default=None,
        help=(
            "Git ref to diff against. Defaults to $GWAY_CI_BASE or "
            "origin/main when available."
        ),
    )
    parser.add_argument(
        "--include",
        default="",
        help="Comma/space separated list of additional flags to enable.",
    )
    parser.add_argument(
        "--print-flags",
        action="store_true",
        help="Print computed flags and exit without running tests.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the resolved command without executing it.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Display debug information about flag detection.",
    )

    args, remaining = parser.parse_known_args(argv)
    if remaining and remaining[0] == "--":
        remaining = remaining[1:]

    remaining, manual_flags = _strip_manual_flags(list(remaining))
    repo_root = Path(__file__).resolve().parents[1]

    base_ref = args.base
    if base_ref is None:
        base_ref = os.environ.get("GWAY_CI_BASE", "origin/main")
    if base_ref == "":
        base_ref = None

    changed = gather_changed_files(repo_root, base_ref)
    hits = detect_optional_flags(changed)

    include_flags = set(parse_flag_list(args.include))
    include_flags.update(manual_flags)
    include_flags.update(parse_flag_list(os.environ.get("GW_FORCE_TEST_FLAGS")))

    final_flags = sorted(set(hits) | include_flags)

    if args.verbose:
        if changed:
            print("[ci-tests] changed files:")
            for path in sorted(changed):
                print(f"[ci-tests]   {path}")
        else:
            print("[ci-tests] no changed files detected")
        if hits:
            for flag, paths in hits.items():
                print(
                    f"[ci-tests] enabling flag '{flag}' for: "
                    f"{', '.join(paths)}"
                )
        else:
            print("[ci-tests] no optional flags triggered")

    if args.print_flags:
        print(" ".join(final_flags))
        return 0

    command = ["gway", "test"]
    command.extend(remaining)
    if final_flags:
        command.extend(["--flags", ",".join(sorted(final_flags))])

    if args.verbose or args.dry_run:
        pretty = " ".join(shlex.quote(part) for part in command)
        print(f"[ci-tests] command: {pretty}")

    if args.dry_run:
        return 0

    proc = subprocess.run(command, cwd=repo_root)
    return proc.returncode


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main(sys.argv[1:]))
