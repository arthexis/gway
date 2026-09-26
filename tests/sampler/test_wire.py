import json
import threading
from urllib.request import Request, urlopen

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


def test_wire_registry_reuses_address_for_same_device_and_key(tmp_path):
    module = sampler.load("wire")
    registry = module.Registry(tmp_path / "registry.sqlite3")
    first_token, _ = registry.create_token(device="gway-004", token="T" * 24)
    first, created = registry.enroll(
        device="gway-004",
        public_key="D" * 43 + "=",
        token=first_token,
    )
    second_token, _ = registry.create_token(device="gway-004", token="U" * 24)
    second, recreated = registry.enroll(
        device="gway-004",
        public_key="D" * 43 + "=",
        token=second_token,
    )

    assert created is True
    assert recreated is False
    assert first["address"] == second["address"] == "10.90.0.2/32"


def test_wire_enrollment_token_is_one_time(tmp_path):
    module = sampler.load("wire")
    registry = module.Registry(tmp_path / "registry.sqlite3")
    token, _ = registry.create_token(device="gway-004", token="T" * 24)
    registry.enroll(
        device="gway-004",
        public_key="D" * 43 + "=",
        token=token,
    )

    with pytest.raises(PermissionError, match="already-used"):
        registry.enroll(
            device="gway-004",
            public_key="D" * 43 + "=",
            token=token,
        )


def test_wire_registry_rejects_key_conflict(tmp_path):
    module = sampler.load("wire")
    registry = module.Registry(tmp_path / "registry.sqlite3")
    token, _ = registry.create_token(device="gway-004", token="T" * 24)
    registry.enroll(
        device="gway-004",
        public_key="D" * 43 + "=",
        token=token,
    )
    next_token, _ = registry.create_token(device="gway-004", token="U" * 24)

    with pytest.raises(ValueError, match="another key"):
        registry.enroll(
            device="gway-004",
            public_key="E" * 43 + "=",
            token=next_token,
        )


def test_wire_registry_allocates_distinct_addresses(tmp_path):
    module = sampler.load("wire")
    registry = module.Registry(tmp_path / "registry.sqlite3")
    results = []
    for device, key, token in [
        ("gway-004", "D", "T" * 24),
        ("gway-005", "E", "U" * 24),
    ]:
        issued, _ = registry.create_token(device=device, token=token)
        record, _ = registry.enroll(
            device=device,
            public_key=key * 43 + "=",
            token=issued,
        )
        results.append(record)

    assert [item["address"] for item in results] == [
        "10.90.0.2/32",
        "10.90.0.3/32",
    ]


def test_wire_w3_operations_have_mutation_metadata():
    gateway = Gateway()
    module = sampler.load("wire")
    module.register(gateway)

    assert gateway.ops.resolve("wire.server.token").mutates is True
    assert gateway.ops.resolve("wire.client.enroll").mutates is True


def _enroll_device(controller, registry, tmp_path, monkeypatch, device, key):
    module = sampler.load("wire")
    store = module.Registry(registry)
    token, _ = store.create_token(device=device)
    record, _ = store.enroll(
        device=device,
        public_key=key * 43 + "=",
        token=token,
    )
    return record


def test_wire_sync_preserves_manual_peers_and_reconciles_managed_devices(tmp_path, monkeypatch):
    gateway = Gateway()
    module = sampler.load("wire")
    controller = module.register(gateway)
    registry = tmp_path / "registry.sqlite3"
    config = tmp_path / "gway.conf"
    manual_key = "M" * 43 + "="
    config.write_text(
        "[Interface]\n"
        "Address = 10.90.0.1/24\n\n"
        "[Peer]\n"
        f"PublicKey = {manual_key}\n"
        "AllowedIPs = 10.90.0.9/32\n",
        encoding="utf-8",
    )

    _enroll_device(controller, registry, tmp_path, monkeypatch, "gway-004", "D")
    result = controller.sync(registry=registry, config=config)

    text = config.read_text(encoding="utf-8")
    assert result["changed"] is True
    assert manual_key in text
    assert "AllowedIPs = 10.90.0.9/32" in text
    assert "# BEGIN gway wire peer: gway-004" in text
    assert "AllowedIPs = 10.90.0.2/32" in text

    second = controller.sync(registry=registry, config=config)
    assert second["changed"] is False


def test_wire_enrollment_avoids_manual_peer_addresses(tmp_path):
    gateway = Gateway()
    module = sampler.load("wire")
    controller = module.register(gateway, which=lambda name: None)
    registry = tmp_path / "registry.sqlite3"
    config = tmp_path / "gway.conf"
    config.write_text(
        "[Interface]\nAddress = 10.90.0.1/24\n\n"
        "[Peer]\nPublicKey = " + "M" * 43 + "=\n"
        "AllowedIPs = 10.90.0.2/32\n",
        encoding="utf-8",
    )
    token = controller.token(device="gway-004", registry=registry)["token"]

    result = controller.accept_enrollment(
        "gway-004",
        public_key="D" * 43 + "=",
        token=token,
        registry=registry,
        config=config,
        server_public_key="S" * 43 + "=",
        server_endpoint="vpn.example.test:51820",
    )

    assert result["address"] == "10.90.0.3/32"


def test_wire_revoke_is_peer_scoped_and_idempotent(tmp_path, monkeypatch):
    gateway = Gateway()
    module = sampler.load("wire")
    controller = module.register(gateway)
    registry = tmp_path / "registry.sqlite3"
    config = tmp_path / "gway.conf"
    config.write_text("[Interface]\nAddress = 10.90.0.1/24\n", encoding="utf-8")

    _enroll_device(controller, registry, tmp_path, monkeypatch, "gway-004", "D")
    _enroll_device(controller, registry, tmp_path, monkeypatch, "gway-005", "E")
    controller.sync(registry=registry, config=config)

    first = controller.revoke("gway-004", registry=registry, config=config)
    text = config.read_text(encoding="utf-8")
    assert first["revoked"] is True
    assert first["already_revoked"] is False
    assert "gway-004" not in text
    assert "gway-005" in text

    second = controller.revoke("gway-004", registry=registry, config=config)
    assert second["already_revoked"] is True
    assert "gway-005" in config.read_text(encoding="utf-8")


def test_wire_devices_is_read_only_and_deterministic(tmp_path, monkeypatch):
    gateway = Gateway()
    module = sampler.load("wire")
    controller = module.register(gateway)
    registry = tmp_path / "registry.sqlite3"

    _enroll_device(controller, registry, tmp_path, monkeypatch, "gway-005", "E")
    _enroll_device(controller, registry, tmp_path, monkeypatch, "gway-004", "D")

    rows = controller.devices(registry=registry)

    assert [row["device"] for row in rows] == ["gway-004", "gway-005"]
    assert gateway.ops.resolve("wire.server.devices").mutates is False


def test_wire_w4_mutation_metadata():
    gateway = Gateway()
    module = sampler.load("wire")
    module.register(gateway)

    assert gateway.ops.resolve("wire.sync").mutates is True
    assert gateway.ops.resolve("wire.server.sync").mutates is True
    assert gateway.ops.resolve("wire.server.revoke").mutates is True


def test_wire_watchtower_deploy_uses_register_arthexis_com_by_default(
    tmp_path, monkeypatch
):
    gateway = Gateway()
    module = sampler.load("wire")
    controller = module.register(gateway)
    registry = tmp_path / "registry.sqlite3"
    config = tmp_path / "gway.conf"

    monkeypatch.setattr(gateway, "render", lambda template, *, to, **kwargs: to)
    monkeypatch.setattr(
        controller,
        "status",
        lambda interface="gway", debug=False, config=None, mutate=False: {
            "interface": interface,
            "configured": True,
            "running": True,
        },
    )

    result = controller.deploy_server(
        private_key="PRIVATE",
        registry=registry,
        config=config,
    )

    assert result["role"] == "watchtower"
    assert result["central"] is True
    assert result["domain"] == "register.arthexis.com"
    assert result["enrollment_url"] == "https://register.arthexis.com/v1/enroll"
    assert result["registry"] == str(registry)
    assert registry.is_file()
    assert result["readiness"]["checks"]["wireguard"] is True
    assert result["readiness"]["checks"]["registry"] is True


def test_wire_server_check_can_gate_existing_dns_record(tmp_path, monkeypatch):
    gateway = Gateway()
    module = sampler.load("wire")
    controller = module.register(gateway)
    registry = tmp_path / "registry.sqlite3"
    module.Registry(registry).connect().close()

    monkeypatch.setattr(
        controller,
        "status",
        lambda interface="gway", debug=False, mutate=False: {
            "interface": interface,
            "configured": True,
            "running": True,
        },
    )
    calls = []

    def ready(domain, *, type, value, backend, zone):
        calls.append((domain, type, value, backend, zone))
        return True

    monkeypatch.setattr(gateway._dns_controller, "ready", ready)

    result = controller.server_check(
        registry=registry,
        public_address="203.0.113.10",
    )

    assert result["ready"] is True
    assert result["domain"] == "register.arthexis.com"
    assert result["enrollment_url"] == "https://register.arthexis.com/v1/enroll"
    assert calls == [
        (
            "register.arthexis.com",
            "A",
            "203.0.113.10",
            "godaddy",
            "arthexis.com",
        )
    ]


def test_wire_server_check_is_read_only_and_deploy_mutates():
    gateway = Gateway()
    module = sampler.load("wire")
    module.register(gateway)

    assert gateway.ops.resolve("wire.server.check").mutates is False
    assert gateway.ops.resolve("wire.server.deploy").mutates is True


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


def test_wire_devices_missing_registry_is_read_only(tmp_path):
    gateway = Gateway()
    module = sampler.load("wire")
    controller = module.register(gateway)
    registry = tmp_path / "missing" / "registry.sqlite3"

    assert controller.devices(registry=registry) == []
    assert not registry.exists()
    assert not registry.parent.exists()


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
