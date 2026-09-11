from __future__ import annotations

import pytest

from gway import bootstrap, cli
from gway.explain import record


def test_extract_explain_flag_is_global_until_literal_boundary() -> None:
    args, explain = bootstrap._extract_explain_flag(
        ["demo", "-e", "run", "--explain", "--", "--explain"]
    )

    assert explain is True
    assert args == ["demo", "run", "--", "--explain"]


def test_bootstrap_explain_renders_trace_and_failure(capsys, monkeypatch) -> None:
    def fake_main(argv):
        assert argv == ["demo", "run"]
        record("test.step", "ran fake command", argv=list(argv))
        return 2

    monkeypatch.setattr(cli, "main", fake_main)

    assert bootstrap.main(["--explain", "demo", "run"]) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Explain:" in captured.err
    assert "test.step: ran fake command" in captured.err
    assert "execution.failure: command exited with non-zero status" in captured.err


def test_bootstrap_explain_does_not_count_system_exit_as_failure(capsys, monkeypatch) -> None:
    def fake_main(argv):
        raise SystemExit(0)

    monkeypatch.setattr(cli, "main", fake_main)

    with pytest.raises(SystemExit) as exc_info:
        bootstrap.main(["--explain", "--help"])

    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "Explain:" in captured.err
    assert "execution.failure" not in captured.err


def test_bootstrap_without_explain_does_not_render_trace(capsys, monkeypatch) -> None:
    monkeypatch.setattr(cli, "main", lambda argv: 0)

    assert bootstrap.main(["demo", "run"]) == 0

    captured = capsys.readouterr()
    assert "Explain:" not in captured.err
