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


def test_wire_server_token_and_client_enroll_reuse_address(tmp_path, monkeypatch):
    gateway = Gateway()
    module = sampler.load("wire")
    controller = module.register(gateway)
    registry = tmp_path / "registry.sqlite3"
    rendered = []

    monkeypatch.setattr(
        gateway,
        "render",
        lambda template, *, to, sudo=False, rollback=None: (
            rendered.append((template, to, dict(gateway.context))) or to
        ),
    )

    token = controller.token(
        device="gway-004",
        ttl=120,
        registry=registry,
    )["token"]

    first = controller.enroll(
        "gway-004",
        public_key="D" * 43 + "=",
        private_key="PRIVATE",
        token=token,
        server_public_key="S" * 43 + "=",
        server_endpoint="vpn.example.test:51820",
        registry=registry,
        to=tmp_path / "client.conf",
    )

    second_token = controller.token(
        device="gway-004",
        ttl=120,
        registry=registry,
    )["token"]
    second = controller.enroll(
        "gway-004",
        public_key="D" * 43 + "=",
        private_key="PRIVATE",
        token=second_token,
        server_public_key="S" * 43 + "=",
        server_endpoint="vpn.example.test:51820",
        registry=registry,
        to=tmp_path / "client.conf",
    )

    assert first["address"] == "10.90.0.2/32"
    assert second["address"] == first["address"]
    assert first["created"] is True
    assert second["created"] is False
    assert "PRIVATE" not in repr(first)
    assert "PRIVATE" not in repr(second)
    assert rendered[-1][2]["wire_client_private_key"] == "PRIVATE"
    assert "wire_client_private_key" not in gateway.context


def test_wire_enrollment_token_is_one_time(tmp_path, monkeypatch):
    gateway = Gateway()
    module = sampler.load("wire")
    controller = module.register(gateway)
    registry = tmp_path / "registry.sqlite3"
    monkeypatch.setattr(gateway, "render", lambda template, *, to, **kwargs: to)

    token = controller.token(device="gway-004", registry=registry)["token"]
    kwargs = dict(
        public_key="D" * 43 + "=",
        private_key="PRIVATE",
        token=token,
        server_public_key="S" * 43 + "=",
        server_endpoint="vpn.example.test:51820",
        registry=registry,
        to=tmp_path / "client.conf",
    )
    controller.enroll("gway-004", **kwargs)

    with pytest.raises(PermissionError, match="already-used"):
        controller.enroll("gway-004", **kwargs)


def test_wire_enrollment_rejects_key_conflict(tmp_path, monkeypatch):
    gateway = Gateway()
    module = sampler.load("wire")
    controller = module.register(gateway)
    registry = tmp_path / "registry.sqlite3"
    monkeypatch.setattr(gateway, "render", lambda template, *, to, **kwargs: to)

    token = controller.token(device="gway-004", registry=registry)["token"]
    controller.enroll(
        "gway-004",
        public_key="D" * 43 + "=",
        private_key="PRIVATE",
        token=token,
        server_public_key="S" * 43 + "=",
        server_endpoint="vpn.example.test:51820",
        registry=registry,
        to=tmp_path / "client.conf",
    )
    next_token = controller.token(device="gway-004", registry=registry)["token"]

    with pytest.raises(ValueError, match="another key"):
        controller.enroll(
            "gway-004",
            public_key="E" * 43 + "=",
            private_key="PRIVATE",
            token=next_token,
            server_public_key="S" * 43 + "=",
            server_endpoint="vpn.example.test:51820",
            registry=registry,
            to=tmp_path / "client.conf",
        )


def test_wire_enrollment_allocates_distinct_addresses(tmp_path, monkeypatch):
    gateway = Gateway()
    module = sampler.load("wire")
    controller = module.register(gateway)
    registry = tmp_path / "registry.sqlite3"
    monkeypatch.setattr(gateway, "render", lambda template, *, to, **kwargs: to)

    results = []
    for index, key in [(4, "D"), (5, "E")]:
        device = f"gway-00{index}"
        token = controller.token(device=device, registry=registry)["token"]
        results.append(
            controller.enroll(
                device,
                public_key=key * 43 + "=",
                private_key="PRIVATE",
                token=token,
                server_public_key="S" * 43 + "=",
                server_endpoint="vpn.example.test:51820",
                registry=registry,
                to=tmp_path / f"{device}.conf",
            )
        )

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
    monkeypatch.setattr(controller.gateway, "render", lambda template, *, to, **kwargs: to)
    token = controller.token(device=device, registry=registry)["token"]
    return controller.enroll(
        device,
        public_key=key * 43 + "=",
        private_key="PRIVATE",
        token=token,
        server_public_key="S" * 43 + "=",
        server_endpoint="vpn.example.test:51820",
        registry=registry,
        to=tmp_path / f"{device}.conf",
    )


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


def test_wire_enrollment_avoids_manual_peer_addresses(tmp_path, monkeypatch):
    gateway = Gateway()
    module = sampler.load("wire")
    controller = module.register(gateway)
    registry = tmp_path / "registry.sqlite3"
    config = tmp_path / "gway.conf"
    config.write_text(
        "[Interface]\nAddress = 10.90.0.1/24\n\n"
        "[Peer]\nPublicKey = " + "M" * 43 + "=\n"
        "AllowedIPs = 10.90.0.2/32\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(gateway, "render", lambda template, *, to, **kwargs: to)
    token = controller.token(device="gway-004", registry=registry)["token"]

    result = controller.enroll(
        "gway-004",
        public_key="D" * 43 + "=",
        private_key="PRIVATE",
        token=token,
        server_public_key="S" * 43 + "=",
        server_endpoint="vpn.example.test:51820",
        registry=registry,
        server_config=config,
        to=tmp_path / "client.conf",
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
