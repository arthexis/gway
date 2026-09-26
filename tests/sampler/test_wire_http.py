import json
import threading
from types import SimpleNamespace
from urllib.request import Request, urlopen

import pytest

from gway import Gateway
from gway import sampler


def _serve(server):
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread


def test_wire_enrollment_http_accepts_token_and_reconciles_peer(tmp_path):
    gateway = Gateway()
    module = sampler.load("wire")
    controller = module.register(gateway)
    registry = tmp_path / "registry.sqlite3"
    config = tmp_path / "gway.conf"
    config.write_text("[Interface]\nAddress = 10.90.0.1/24\n", encoding="utf-8")

    token = controller.token(device="gway-004", registry=registry)["token"]
    server = module.build_enrollment_server(
        controller,
        host="127.0.0.1",
        port=0,
        domain="register.arthexis.com",
        registry=registry,
        config=config,
        server_public_key="S" * 43 + "=",
        server_endpoint="vpn.arthexis.com:51820",
    )
    thread = _serve(server)
    host, port = server.server_address
    try:
        request = Request(
            f"http://{host}:{port}/v1/enroll",
            data=json.dumps(
                {
                    "device": "gway-004",
                    "public_key": "D" * 43 + "=",
                    "token": token,
                }
            ).encode("utf-8"),
            headers={"content-type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert payload["device"] == "gway-004"
    assert payload["address"] == "10.90.0.2/32"
    assert payload["server_public_key"] == "S" * 43 + "="
    assert payload["server_endpoint"] == "vpn.arthexis.com:51820"
    assert "token" not in payload
    assert "# BEGIN gway wire peer: gway-004" in config.read_text(encoding="utf-8")


def test_wire_enrollment_http_health_uses_register_domain(tmp_path):
    gateway = Gateway()
    module = sampler.load("wire")
    controller = module.register(gateway)
    registry = tmp_path / "registry.sqlite3"
    config = tmp_path / "gway.conf"
    config.write_text("[Interface]\n", encoding="utf-8")

    server = module.build_enrollment_server(
        controller,
        host="127.0.0.1",
        port=0,
        registry=registry,
        config=config,
        server_public_key="S" * 43 + "=",
    )
    thread = _serve(server)
    host, port = server.server_address
    try:
        with urlopen(f"http://{host}:{port}/health", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert payload == {
        "ok": True,
        "service": "wire-enrollment",
        "domain": "register.arthexis.com",
    }


def test_wire_enrollment_service_has_stable_gway_service_identity():
    gateway = Gateway()
    module = sampler.load("wire")
    module.register(gateway)

    service = gateway._service_presets[("gway", "wire-enroll")]

    assert service.launchable.name == "wire.server.serve"
    assert service.description == "Watchtower Wire client enrollment service"


def test_wire_enrollment_http_rejects_reused_token(tmp_path):
    gateway = Gateway()
    module = sampler.load("wire")
    controller = module.register(gateway, which=lambda name: None)
    registry = tmp_path / "registry.sqlite3"
    config = tmp_path / "gway.conf"
    config.write_text("[Interface]\nAddress = 10.90.0.1/24\n", encoding="utf-8")
    token = controller.token(device="gway-004", registry=registry)["token"]

    first = controller.accept_enrollment(
        "gway-004",
        public_key="D" * 43 + "=",
        token=token,
        registry=registry,
        config=config,
        server_public_key="S" * 43 + "=",
        server_endpoint="vpn.arthexis.com:51820",
    )
    assert first["created"] is True

    with pytest.raises(PermissionError, match="already-used"):
        controller.accept_enrollment(
            "gway-004",
            public_key="D" * 43 + "=",
            token=token,
            registry=registry,
            config=config,
            server_public_key="S" * 43 + "=",
            server_endpoint="vpn.arthexis.com:51820",
        )


def test_wire_enrollment_token_survives_reconciliation_failure(tmp_path):
    gateway = Gateway()
    module = sampler.load("wire")
    controller = module.register(gateway, which=lambda name: None)
    registry = tmp_path / "registry.sqlite3"
    config = tmp_path / "missing.conf"
    token = controller.token(device="gway-004", registry=registry)["token"]

    with pytest.raises(FileNotFoundError):
        controller.accept_enrollment(
            "gway-004",
            public_key="D" * 43 + "=",
            token=token,
            registry=registry,
            config=config,
            server_public_key="S" * 43 + "=",
            server_endpoint="vpn.arthexis.com:51820",
        )

    config.write_text("[Interface]\nAddress = 10.90.0.1/24\n", encoding="utf-8")
    retry = controller.accept_enrollment(
        "gway-004",
        public_key="D" * 43 + "=",
        token=token,
        registry=registry,
        config=config,
        server_public_key="S" * 43 + "=",
        server_endpoint="vpn.arthexis.com:51820",
    )
    assert retry["address"] == "10.90.0.2/32"


def test_wire_enrollment_applies_peer_to_running_interface(tmp_path):
    gateway = Gateway()
    module = sampler.load("wire")
    results = [
        SimpleNamespace(returncode=0, stdout="interface: gway\n", stderr=""),
        SimpleNamespace(returncode=0, stdout="", stderr=""),
    ]

    class SequenceRunner:
        def __init__(self):
            self.calls = []

        def __call__(self, argv):
            self.calls.append(tuple(argv))
            return results.pop(0)

    runner = SequenceRunner()
    controller = module.register(
        gateway,
        runner=runner,
        which=lambda name: f"/usr/bin/{name}" if name == "wg" else None,
    )
    registry = tmp_path / "registry.sqlite3"
    config = tmp_path / "gway.conf"
    config.write_text("[Interface]\nAddress = 10.90.0.1/24\n", encoding="utf-8")
    token = controller.token(device="gway-004", registry=registry)["token"]

    result = controller.accept_enrollment(
        "gway-004",
        public_key="D" * 43 + "=",
        token=token,
        registry=registry,
        config=config,
        server_public_key="S" * 43 + "=",
        server_endpoint="vpn.arthexis.com:51820",
    )

    assert result["peer_applied"] is True
    assert runner.calls == [
        ("/usr/bin/wg", "show", "gway"),
        (
            "/usr/bin/wg",
            "set",
            "gway",
            "peer",
            "D" * 43 + "=",
            "allowed-ips",
            "10.90.0.2/32",
        ),
    ]


