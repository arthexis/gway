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
