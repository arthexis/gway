from __future__ import annotations

import os

from gway import bootstrap


def test_bootstrap_disables_git_terminal_prompts_for_all_cli_verbs(monkeypatch) -> None:
    calls: list[list[str] | None] = []

    def fake_main(argv=None):
        calls.append(argv)
        return 17

    monkeypatch.setenv("GIT_TERMINAL_PROMPT", "1")
    monkeypatch.setattr("gway.cli.main", fake_main)

    result = bootstrap.main(["install", "arthexis"])

    assert result == 17
    assert calls == [["install", "arthexis"]]
    assert os.environ["GIT_TERMINAL_PROMPT"] == "0"


def test_upgrade_gway_is_normalized_to_self_upgrade(monkeypatch) -> None:
    calls: list[list[str] | None] = []

    def fake_main(argv=None):
        calls.append(argv)
        return 0

    monkeypatch.setattr("gway.cli.main", fake_main)

    assert bootstrap.main(["upgrade", "gway"]) == 0
    assert calls == [["upgrade", "--self"]]


def test_upgrade_gway_alias_allows_upgrade_flags(monkeypatch) -> None:
    calls: list[list[str] | None] = []

    def fake_main(argv=None):
        calls.append(argv)
        return 0

    monkeypatch.setattr("gway.cli.main", fake_main)

    assert bootstrap.main(["upgrade", "--force", "gway"]) == 0
    assert calls == [["upgrade", "--force", "--self"]]


def test_non_upgrade_gway_argument_is_unchanged(monkeypatch) -> None:
    calls: list[list[str] | None] = []

    def fake_main(argv=None):
        calls.append(argv)
        return 0

    monkeypatch.setattr("gway.cli.main", fake_main)

    assert bootstrap.main(["info", "gway"]) == 0
    assert calls == [["info", "gway"]]
