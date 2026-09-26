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


def test_wire_provision_uses_gway_render_without_returning_private_key(monkeypatch):
    gateway = Gateway()
    module = sampler.load("wire")
    controller = module.register(gateway)
    calls = []

    def render(template, *, to, sudo=False, rollback=None, mode=None):
        calls.append(
            {
                "template": template,
                "to": to,
                "sudo": sudo,
                "rollback": rollback,
                "mode": mode,
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
    assert calls[0]["mode"] == 0o600
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


def test_wire_templates_render_literal_headers_and_owner_only_mode(tmp_path):
    gateway = Gateway()
    module = sampler.load("wire")
    controller = module.register(gateway)
    destination = tmp_path / "gway.conf"

    controller.provision(
        address="10.90.0.1/24",
        private_key="PRIVATE",
        to=destination,
    )

    text = destination.read_text(encoding="utf-8")
    assert text.startswith("[Interface]\n")
    assert destination.stat().st_mode & 0o777 == 0o600


