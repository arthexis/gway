from __future__ import annotations

from pathlib import Path

from gway.config import GwayPaths
from gway.project import Project
from gway.registry import Registry
from gway import sigils as gway_sigils


def _context(tmp_path: Path, monkeypatch):
    project_root = tmp_path / "network"
    project_root.mkdir()
    (project_root / "values.py").write_text(
        "calls = 0\n"
        "\n"
        "def ip(interface):\n"
        "    global calls\n"
        "    calls += 1\n"
        "    return f'ip:{interface}'\n"
        "\n"
        "def describe(interface, metric='state'):\n"
        "    return f'{interface}:{metric}'\n"
        "\n"
        "def tuple_value(values):\n"
        "    return '|'.join(values)\n",
        encoding="utf-8",
    )
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    Registry(paths).register(
        Project(
            name="network",
            path=project_root,
            adapter_type="python",
            adapter_config={"module": "values"},
        )
    )
    monkeypatch.setattr(gway_sigils, "_SIGILS_SUPPORTS_PROVIDER_CALLS", True)
    return gway_sigils.gway_context(paths)


def test_provider_exposes_required_command_as_approved_callable(tmp_path, monkeypatch) -> None:
    context = _context(tmp_path, monkeypatch)
    command = context["network"].resolve("ip")

    assert command.__sigils_safe_callable__ is True
    assert command.__sigils_requires_args__ is True
    assert command("wlan0") == "ip:wlan0"


def test_provider_supports_keyword_arguments(tmp_path, monkeypatch) -> None:
    context = _context(tmp_path, monkeypatch)
    command = context["network"].resolve("describe")

    assert command(interface="wlan0", metric="count") == "wlan0:count"


def test_provider_preserves_tuple_arguments(tmp_path, monkeypatch) -> None:
    context = _context(tmp_path, monkeypatch)
    command = context["network"].resolve("tuple-value")

    assert command(("wlan0", "eth0")) == "wlan0|eth0"


def test_parameterized_provider_calls_memoize_by_arguments(tmp_path, monkeypatch) -> None:
    context = _context(tmp_path, monkeypatch)
    command = context["network"].resolve("ip")

    assert command("wlan0") == "ip:wlan0"
    assert command("wlan0") == "ip:wlan0"
    assert command("eth0") == "ip:eth0"

    module = command.command.adapter_data.__module__
    imported = __import__(module)
    assert imported.calls == 2
