import json

from gway.console import _human_output


def test_human_output_collapses_success_envelopes_and_formats_sections():
    output = _human_output(
        {
            "node": {
                "status": "ok",
                "available": True,
                "result": {
                    "role": "control",
                    "runtime": {"version": "1.2.3", "managed": True},
                },
                "error": None,
            },
            "wire": {
                "status": "error",
                "available": True,
                "result": None,
                "error": {"type": "ConnectionError", "message": "offline"},
            },
            "changed_at": None,
        }
    )

    assert "Node" in output
    assert "Role: control" in output
    assert "Runtime" in output
    assert "Version: 1.2.3" in output
    assert "Managed: yes" in output
    assert "Wire" in output
    assert "error: offline" in output
    assert "Available:" not in output
    assert "Result" not in output
    assert "Changed at: —" in output


def test_watch_cli_uses_generic_human_renderer(run_cli, tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "demo"

[tool.gway.variables]
role = "control"
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    status, stdout, stderr = run_cli("watch", "--only", "node")

    assert status == 0
    assert stderr == ""
    assert "Node" in stdout
    assert "Role: control" in stdout
    assert "Health" in stdout
    assert "Status: ok" in stdout
    assert "Available:" not in stdout
    assert '"node"' not in stdout


def test_lowercase_j_and_json_are_exact_cli_aliases(run_cli):
    short_status, short_stdout, short_stderr = run_cli("-j", "version")
    long_status, long_stdout, long_stderr = run_cli("--json", "version")

    assert short_status == long_status == 0
    assert short_stderr == long_stderr == ""
    assert short_stdout == long_stdout
    assert json.loads(short_stdout)


def test_timed_json_keeps_stdout_machine_readable(run_cli, tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "demo"

[tool.gway.variables]
role = "control"
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    status, stdout, _ = run_cli("-t", "-j", "watch", "--only", "node")

    assert status == 0
    payload = json.loads(stdout)
    assert set(payload) == {"node", "health", "changed_at", "cursor"}
    assert "[timed]" not in stdout
