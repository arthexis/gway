from gway import Gateway
from gway import sampler


class FakeRunner:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def __call__(self, argv):
        self.calls.append(tuple(argv))
        return self.result


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




def test_watchtower_deploy_reuses_existing_private_key(tmp_path, monkeypatch):
    gateway = Gateway()
    module = sampler.load("wire")
    controller = module.register(gateway, which=lambda name: None)
    registry = tmp_path / "registry.sqlite3"
    config = tmp_path / "gway.conf"
    config.write_text(
        "[Interface]\nAddress = 10.90.0.1/24\nPrivateKey = EXISTING\n",
        encoding="utf-8",
    )
    captured = {}
    monkeypatch.setattr(
        controller,
        "provision",
        lambda interface, **kwargs: (
            captured.update(kwargs) or {"config": str(config)}
        ),
    )
    monkeypatch.setattr(
        controller,
        "server_check",
        lambda **kwargs: {"ready": True},
    )

    controller.deploy_server(registry=registry, config=config)

    assert captured["private_key"] == "EXISTING"


def test_enrollment_service_derives_public_key_from_server_config(tmp_path, monkeypatch):
    gateway = Gateway()
    module = sampler.load("wire")
    controller = module.register(gateway, which=lambda name: "/usr/bin/wg")
    config = tmp_path / "gway.conf"
    config.write_text(
        "[Interface]\nPrivateKey = EXISTING\n",
        encoding="utf-8",
    )
    captured = {}
    fake_server = type(
        "FakeServer",
        (),
        {"serve_forever": lambda self: None, "server_close": lambda self: None},
    )()

    monkeypatch.setattr(
        module,
        "_public_key_from_private",
        lambda private_key, which: "S" * 43 + "=",
    )
    monkeypatch.setattr(
        module,
        "build_enrollment_server",
        lambda controller, **kwargs: (
            captured.update(kwargs) or fake_server
        ),
    )

    controller.serve_enrollment(
        config=config,
        registry=tmp_path / "registry.sqlite3",
    )

    assert captured["server_public_key"] == "S" * 43 + "="
