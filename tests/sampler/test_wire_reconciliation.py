from gway import Gateway
from gway import sampler


class FakeRunner:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def __call__(self, argv):
        self.calls.append(tuple(argv))
        return self.result


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


