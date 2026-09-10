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


def test_bare_install_bootstraps_system_install_before_managed_install(monkeypatch) -> None:
    monkeypatch.delenv("GWAY_SYSTEM_INSTALL", raising=False)
    monkeypatch.setattr(bootstrap, "_bootstrap_system_install", lambda: 23)

    assert bootstrap.main(["install"]) == 23


def test_bare_install_uses_normal_cli_guidance_when_system_installed(monkeypatch) -> None:
    calls: list[list[str] | None] = []

    def fake_main(argv=None):
        calls.append(argv)
        return 29

    monkeypatch.setenv("GWAY_SYSTEM_INSTALL", "1")
    monkeypatch.setattr("gway.cli.main", fake_main)

    assert bootstrap.main(["install"]) == 29
    assert calls == [["install"]]
