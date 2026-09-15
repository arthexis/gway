from __future__ import annotations

import subprocess
from pathlib import Path

from gway.checkout_clean import clean_managed_checkout, split_clean_arguments


class _Repositories:
    def __init__(self) -> None:
        self.validated: list[tuple[Path, str]] = []

    def validate_checkout(self, checkout: Path, full_name: str) -> None:
        self.validated.append((checkout, full_name))


def _git(checkout: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(checkout), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _repository(tmp_path: Path) -> Path:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    _git(checkout, "init", "--quiet")
    _git(checkout, "config", "user.email", "tests@example.invalid")
    _git(checkout, "config", "user.name", "Gway Tests")
    (checkout / "tracked.txt").write_text("tracked\n", encoding="utf-8")
    _git(checkout, "add", "tracked.txt")
    _git(checkout, "commit", "--quiet", "-m", "initial")
    return checkout


def test_split_clean_arguments_defaults_to_clean_and_strips_override() -> None:
    assert split_clean_arguments(("--mode", "safe")) == (
        True,
        ("--mode", "safe"),
    )
    assert split_clean_arguments(("--mode", "safe", "--no-clean")) == (
        False,
        ("--mode", "safe"),
    )
    assert split_clean_arguments(("--no-clean", "--clean")) == (True, ())


def test_clean_removes_untracked_tombstones_but_preserves_ignored_state(
    tmp_path: Path,
) -> None:
    checkout = _repository(tmp_path)
    exclude = checkout / ".git" / "info" / "exclude"
    exclude.write_text("runtime-state/\n", encoding="utf-8")
    stale = checkout / "stale-command.py"
    stale.write_text("old\n", encoding="utf-8")
    runtime_state = checkout / "runtime-state"
    runtime_state.mkdir()
    (runtime_state / "state.json").write_text("{}\n", encoding="utf-8")

    repositories = _Repositories()
    clean_managed_checkout(checkout, "arthexis/example", repositories)  # type: ignore[arg-type]

    assert not stale.exists()
    assert (runtime_state / "state.json").exists()
    assert repositories.validated == [(checkout, "arthexis/example")]


def test_clean_does_not_reset_tracked_local_changes(tmp_path: Path) -> None:
    checkout = _repository(tmp_path)
    tracked = checkout / "tracked.txt"
    tracked.write_text("locally modified\n", encoding="utf-8")
    stale = checkout / "stale.txt"
    stale.write_text("stale\n", encoding="utf-8")

    clean_managed_checkout(checkout, "arthexis/example", _Repositories())  # type: ignore[arg-type]

    assert tracked.read_text(encoding="utf-8") == "locally modified\n"
    assert not stale.exists()
    status = subprocess.run(
        ["git", "-C", str(checkout), "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert "tracked.txt" in status
