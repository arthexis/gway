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


def test_wire_client_enroll_uses_public_api_and_renders_private_config(
    tmp_path, monkeypatch
):
    gateway = Gateway()
    module = sampler.load("wire")
    controller = module.register(gateway)
    rendered = []
    posted = []

    monkeypatch.setattr(
        module,
        "_post_enrollment",
        lambda url, payload: (
            posted.append((url, payload))
            or {
                "device": "gway-004",
                "address": "10.90.0.2/32",
                "public_key": "D" * 43 + "=",
                "server_public_key": "S" * 43 + "=",
                "server_endpoint": "vpn.example.test:51820",
                "server_tunnel_ip": "10.90.0.1",
                "created": True,
            }
        ),
    )
    monkeypatch.setattr(
        gateway,
        "render",
        lambda template, *, to, mode=None, **kwargs: (
            rendered.append((template, to, mode, dict(gateway.context))) or to
        ),
    )

    result = controller.enroll(
        "gway-004",
        public_key="D" * 43 + "=",
        private_key="PRIVATE",
        token="T" * 24,
        url="register.example.test",
        to=tmp_path / "client.conf",
    )

    assert posted == [
        (
            "register.example.test",
            {
                "device": "gway-004",
                "public_key": "D" * 43 + "=",
                "token": "T" * 24,
            },
        )
    ]
    assert result["address"] == "10.90.0.2/32"
    assert "PRIVATE" not in repr(result)
    assert rendered[0][2] == 0o600
    assert rendered[0][3]["wire_client_private_key"] == "PRIVATE"
    assert "wire_client_private_key" not in gateway.context


def test_wire_client_enroll_accepts_token_file(tmp_path, monkeypatch):
    gateway = Gateway()
    module = sampler.load("wire")
    controller = module.register(gateway)
    token_file = tmp_path / "token"
    token_file.write_text("T" * 24 + "\n", encoding="utf-8")
    seen = {}

    def post(url, payload):
        seen.update(url=url, payload=payload)
        return {
            "address": "10.90.0.2/32",
            "server_public_key": "S" * 43 + "=",
            "server_endpoint": "vpn.example.test:51820",
            "server_tunnel_ip": "10.90.0.1",
            "created": True,
        }

    monkeypatch.setattr(module, "_post_enrollment", post)
    monkeypatch.setattr(gateway, "render", lambda template, *, to, **kwargs: to)

    controller.enroll(
        "gway-004",
        public_key="D" * 43 + "=",
        private_key="PRIVATE",
        token_file=token_file,
        to=tmp_path / "client.conf",
    )

    assert seen["payload"]["token"] == "T" * 24
    assert seen["url"] == "https://register.arthexis.com/v1/enroll"


def test_wire_w3_operations_have_mutation_metadata():
    gateway = Gateway()
    module = sampler.load("wire")
    module.register(gateway)

    assert gateway.ops.resolve("wire.server.token").mutates is True
    assert gateway.ops.resolve("wire.client.enroll").mutates is True


