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


def test_wire_sampler_loads_lazily_for_root_status():
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
    module.register(gateway, runner=runner, which=lambda name: f"/usr/bin/{name}")

    result = gateway("wire status")

    assert result == {
        "interface": "gway",
        "configured": True,
        "running": True,
        "public_key": "PUB",
        "listen_port": "51820",
        "peer_count": 1,
    }
    assert runner.calls == [("/usr/bin/wg", "show", "gway")]


def test_wire_aliases_preserve_legacy_project_names():
    gateway = Gateway()
    module = sampler.load("wire")
    runner = FakeRunner(SimpleNamespace(returncode=1, stdout="", stderr="missing"))
    module.register(gateway, runner=runner, which=lambda name: f"/usr/bin/{name}")

    assert gateway("wire status") == gateway("wireguard status")
    assert gateway("wire status") == gateway("wg status")


@pytest.mark.parametrize("command", ["wire client status", "wire server status"])
def test_wire_role_status_family_is_available(command):
    gateway = Gateway()
    module = sampler.load("wire")
    runner = FakeRunner(
        SimpleNamespace(returncode=0, stdout="interface: gway\n", stderr="")
    )
    module.register(gateway, runner=runner, which=lambda name: f"/usr/bin/{name}")

    result = gateway(command)

    assert result["interface"] == "gway"
    assert result["configured"] is True


def test_wire_status_is_non_mutating():
    gateway = Gateway()
    module = sampler.load("wire")
    module.register(gateway, runner=lambda argv: None, which=lambda name: None)

    assert gateway.ops.resolve("wire.status").mutates is False
    assert gateway.ops.resolve("wire.check").mutates is False
    assert gateway.ops.resolve("wire.provision").mutates is True


def test_wire_provision_uses_gway_render_without_returning_private_key(monkeypatch):
    gateway = Gateway()
    module = sampler.load("wire")
    controller = module.register(gateway)
    calls = []

    def render(template, *, to, sudo=False, rollback=None):
        calls.append(
            {
                "template": template,
                "to": to,
                "sudo": sudo,
                "rollback": rollback,
                "context": dict(gateway.context),
            }
        )
        return to

    monkeypatch.setattr(gateway, "render", render)

    result = controller.provision(
        "wg-test",
        address="10.90.0.1/24",
        private_key="PRIVATE",
        listen_port=51821,
        to="/tmp/wg-test.conf",
        rollback="wire",
    )

    assert result == {
        "interface": "wg-test",
        "address": "10.90.0.1/24",
        "listen_port": 51821,
        "config": "/tmp/wg-test.conf",
    }
    assert "private_key" not in result
    assert calls[0]["context"]["wire_private_key"] == "PRIVATE"
    assert calls[0]["rollback"] == "wire"
    assert "wire_private_key" not in gateway.context


def test_wire_provision_validates_port_before_render(monkeypatch):
    gateway = Gateway()
    module = sampler.load("wire")
    controller = module.register(gateway)
    called = False

    def render(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(gateway, "render", render)

    with pytest.raises(ValueError, match="listen_port"):
        controller.provision(
            address="10.90.0.1/24",
            private_key="PRIVATE",
            listen_port=70000,
        )

    assert called is False
