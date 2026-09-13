from __future__ import annotations

import os

from gway import bootstrap


def test_bootstrap_disables_git_terminal_prompts_for_cli_fallback(monkeypatch) -> None:
    calls: list[list[str] | None] = []

    def fake_main(argv=None):
        calls.append(argv)
        return 17

    monkeypatch.setenv("GIT_TERMINAL_PROMPT", "1")
    monkeypatch.setattr("gway.cli.main", fake_main)

    result = bootstrap.main(["list"])

    assert result == 17
    assert calls == [["list"]]
    assert os.environ["GIT_TERMINAL_PROMPT"] == "0"


def test_bare_install_keeps_project_required_guidance(capsys) -> None:
    result = bootstrap.main(["install"])

    assert result == 2
    stderr = capsys.readouterr().err
    assert "the following arguments are required: project" in stderr
    assert "gway install --self" in stderr
    assert "gway install gway" in stderr


def _capture_runtime(monkeypatch):
    calls: list[tuple[list[str], bool]] = []

    class FakeRuntime:
        def execute(self, tokens, *, interactive=False, **kwargs):
            calls.append((list(tokens), interactive))
            return {
                "status": "upgraded",
                "name": "gway",
                "repository": "arthexis/gway",
                "revision": "main",
            }

    monkeypatch.setattr("gway.runtime.GwayRuntime", FakeRuntime)
    monkeypatch.setattr(bootstrap, "_render_upgrade_result", lambda result, detail: None)
    return calls


def test_install_self_reuses_self_upgrade_runtime_path(monkeypatch) -> None:
    calls = _capture_runtime(monkeypatch)

    assert bootstrap.main(["install", "--self"]) == 0
    assert calls == [(["upgrade", "gway"], False)]


def test_install_gway_reuses_self_upgrade_runtime_path(monkeypatch) -> None:
    calls = _capture_runtime(monkeypatch)

    assert bootstrap.main(["install", "gway"]) == 0
    assert calls == [(["upgrade", "gway"], False)]


def test_install_gway_preserves_leading_global_flags(monkeypatch) -> None:
    calls = _capture_runtime(monkeypatch)
    rendered: list[bool] = []

    monkeypatch.setattr(
        "gway.cli._render_result",
        lambda result, *, json_output=False, **kwargs: rendered.append(json_output),
    )

    assert bootstrap.main(["--json", "install", "gway"]) == 0
    assert calls == [(["upgrade", "gway"], False)]
    assert rendered == [True]


def test_install_self_preserves_trailing_global_flags(monkeypatch) -> None:
    calls = _capture_runtime(monkeypatch)
    rendered: list[bool] = []

    monkeypatch.setattr(
        "gway.cli._render_result",
        lambda result, *, json_output=False, **kwargs: rendered.append(json_output),
    )

    assert bootstrap.main(["install", "--self", "--json"]) == 0
    assert calls == [(["upgrade", "gway"], False)]
    assert rendered == [True]
