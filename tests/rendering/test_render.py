import os
from pathlib import Path

import pytest

from gway.identity import execution_identity


def test_render_resolves_content_template_name_and_directory_destination(
    gateway,
    tmp_path,
):
    template = tmp_path / "nginx-[name].conf"
    template.write_text(
        "server_name [domain];\nproxy_pass http://[host]:[port];\n",
        encoding="utf-8",
    )
    destination = tmp_path / "sites-available"
    destination.mkdir()
    gateway.context.update(
        {
            "name": "arthexis",
            "domain": "arthexis.com",
            "host": "127.0.0.1",
            "port": 8000,
        }
    )

    result = gateway(
        [
            "render",
            str(template),
            "--to",
            f"{destination}{os.sep}",
        ]
    )

    expected = destination / "nginx-arthexis.conf"
    assert result == expected
    assert expected.read_text(encoding="utf-8") == (
        "server_name arthexis.com;\nproxy_pass http://127.0.0.1:8000;\n"
    )


def test_render_uses_explicit_file_destination_with_sigils(gateway, tmp_path):
    template = tmp_path / "plain.conf"
    template.write_text("name=[name]\n", encoding="utf-8")
    destination = tmp_path / "[name].generated.conf"
    gateway.context["name"] = "sample"

    result = gateway(
        [
            "render",
            str(template),
            "--to",
            str(destination),
        ]
    )

    expected = tmp_path / "sample.generated.conf"
    assert result == expected
    assert expected.read_text(encoding="utf-8") == "name=sample\n"


def test_render_replaces_existing_file_atomically(gateway, tmp_path, monkeypatch):
    template = tmp_path / "template.conf"
    template.write_text("new [value]\n", encoding="utf-8")
    destination = tmp_path / "output.conf"
    destination.write_text("old\n", encoding="utf-8")
    gateway.context["value"] = "content"

    calls = []
    real_replace = os.replace

    def replace(source, target):
        calls.append((Path(source), Path(target)))
        return real_replace(source, target)

    monkeypatch.setattr("gway.rendering.os.replace", replace)

    gateway(["render", str(template), "--to", str(destination)])

    assert destination.read_text(encoding="utf-8") == "new content\n"
    assert len(calls) == 1
    assert calls[0][1] == destination
    assert calls[0][0].parent == destination.parent


def test_render_privileged_write_uses_execution_identity(
    gateway,
    tmp_path,
    host_calls,
):
    template = tmp_path / "template.conf"
    template.write_text("content\n", encoding="utf-8")
    destination = tmp_path / "output.conf"
    result = gateway(
        [
            "render",
            str(template),
            "--to",
            str(destination),
            "--as",
            "www-data",
        ]
    )

    assert result == destination
    assert host_calls[0][0][:5] == ("sudo", "-u", "www-data", "install", "-m")
    assert host_calls[0][1] == {"check": True}
    assert host_calls[1][0][:5] == ("sudo", "-u", "www-data", "mv", "-f")
    assert host_calls[1][1] == {"check": True}
    assert host_calls[2][0] == (
        "sudo",
        "-u",
        "www-data",
        "test",
        "-f",
        str(destination),
    )
    assert host_calls[2][1] == {"check": True}


def test_render_sudo_is_root_identity(gateway, tmp_path, host_calls):
    template = tmp_path / "template.conf"
    template.write_text("content\n", encoding="utf-8")
    destination = tmp_path / "output.conf"
    gateway(
        [
            "render",
            str(template),
            "--to",
            str(destination),
            "--sudo",
        ]
    )

    assert host_calls[0][0][:2] == ("sudo", "install")


def test_render_rejects_conflicting_execution_identity(gateway, tmp_path):
    template = tmp_path / "template.conf"
    template.write_text("content\n", encoding="utf-8")
    destination = tmp_path / "output.conf"

    with pytest.raises(ValueError, match="conflicts with --as"):
        gateway(
            [
                "render",
                str(template),
                "--to",
                str(destination),
                "--sudo",
                "--as",
                "www-data",
            ]
        )


def test_execution_identity_command_centralizes_prefix():
    identity = execution_identity(as_user="www-data")

    assert identity.command("install", "source", "target") == (
        "sudo",
        "-u",
        "www-data",
        "install",
        "source",
        "target",
    )


def test_privileged_render_verifies_final_destination(
    gateway,
    tmp_path,
    host_calls,
):
    template = tmp_path / "template.conf"
    template.write_text("content\n", encoding="utf-8")
    destination = tmp_path / "output.conf"

    gateway(
        [
            "render",
            str(template),
            "--to",
            str(destination),
            "--as",
            "root",
        ]
    )

    assert host_calls[-1] == (
        ("sudo", "test", "-f", str(destination)),
        {"check": True},
    )
