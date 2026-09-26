from types import SimpleNamespace

import pytest

from gway import Gateway
from gway import sampler


class FakeRunner:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def __call__(self, argv):
        self.calls.append(tuple(argv))
        return self.result


def test_wire_sampler_loads_lazily_for_root_status(tmp_path):
    gateway = Gateway()
    module = sampler.load("wire")
    runner = FakeRunner(
        SimpleNamespace(returncode=0, stdout="interface: gway\n", stderr="")
    )
    module.register(gateway, runner=runner, which=lambda name: f"/usr/bin/{name}")
    config = tmp_path / "gway.conf"
    config.write_text("[Interface]\n", encoding="utf-8")

    result = gateway(f"wire status --config {config}")

    assert result == {
        "interface": "gway",
        "configured": True,
        "config": str(config),
    }
    assert runner.calls == []


def test_wire_debug_status_probes_live_interface(tmp_path):
    gateway = Gateway()
    module = sampler.load("wire")
    runner = FakeRunner(
        SimpleNamespace(
            returncode=0,
            stdout=(
                "interface: gway\n"
                "  public key: PUB\n"
                "  listening port: 51820\n"
                "peer: ONE\n"
            ),
            stderr="",
        )
    )
    controller = module.register(
        gateway, runner=runner, which=lambda name: f"/usr/bin/{name}"
    )
    config = tmp_path / "gway.conf"
    config.write_text("[Interface]\n", encoding="utf-8")

    result = controller.status(config=config, debug=True)

    assert result["configured"] is True
    assert result["running"] is True
    assert result["public_key"] == "PUB"
    assert result["peer_count"] == 1
    assert runner.calls == [("/usr/bin/wg", "show", "gway")]


def test_wire_aliases_preserve_legacy_project_names():
    gateway = Gateway()
    module = sampler.load("wire")
    runner = FakeRunner(SimpleNamespace(returncode=1, stdout="", stderr="missing"))
    module.register(gateway, runner=runner, which=lambda name: f"/usr/bin/{name}")

    assert gateway("wire status") == gateway("wireguard status")
    assert gateway("wire status") == gateway("wg status")
    assert runner.calls == []


@pytest.mark.parametrize("command", ["wire client status", "wire server status"])
def test_wire_role_status_family_is_available_without_live_probe(command):
    gateway = Gateway()
    module = sampler.load("wire")
    runner = FakeRunner(
        SimpleNamespace(returncode=0, stdout="interface: gway\n", stderr="")
    )
    module.register(gateway, runner=runner, which=lambda name: f"/usr/bin/{name}")

    result = gateway(command)

    assert result["interface"] == "gway"
    assert "configured" in result
    assert runner.calls == []


def test_wire_status_is_non_mutating():
    gateway = Gateway()
    module = sampler.load("wire")
    module.register(gateway, runner=lambda argv: None, which=lambda name: None)

    assert gateway.ops.resolve("wire.status").mutates is False
    assert gateway.ops.resolve("wire.check").mutates is False
    assert gateway.ops.resolve("wire.provision").mutates is True


def test_wire_activate_is_idempotent_when_interface_is_running():
    gateway = Gateway()
    module = sampler.load("wire")
    runner = FakeRunner(
        SimpleNamespace(returncode=0, stdout="interface: gway\n", stderr="")
    )
    controller = module.register(
        gateway, runner=runner, which=lambda name: f"/usr/bin/{name}"
    )

    result = controller.activate()

    assert result == {"interface": "gway", "running": True, "changed": False}
    assert runner.calls == [("/usr/bin/wg", "show", "gway")]
