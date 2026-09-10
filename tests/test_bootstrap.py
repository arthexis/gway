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


def test_bare_install_keeps_project_required_guidance(capsys) -> None:
    result = bootstrap.main(["install"])

    assert result == 2
    stderr = capsys.readouterr().err
    assert "the following arguments are required: project" in stderr
    assert "gway install --self" in stderr
    assert "gway install gway" in stderr


def test_install_self_reuses_self_upgrade_path(monkeypatch) -> None:
    calls: list[list[str] | None] = []

    def fake_main(argv=None):
        calls.append(argv)
        return 0

    monkeypatch.setattr("gway.cli.main", fake_main)

    assert bootstrap.main(["install", "--self"]) == 0
    assert calls == [["upgrade", "gway"]]


def test_install_gway_reuses_self_upgrade_path(monkeypatch) -> None:
    calls: list[list[str] | None] = []

    def fake_main(argv=None):
        calls.append(argv)
        return 0

    monkeypatch.setattr("gway.cli.main", fake_main)

    assert bootstrap.main(["install", "gway"]) == 0
    assert calls == [["upgrade", "gway"]]
