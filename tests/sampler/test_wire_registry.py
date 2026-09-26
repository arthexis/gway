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


def test_wire_devices_missing_registry_is_read_only(tmp_path):
    gateway = Gateway()
    module = sampler.load("wire")
    controller = module.register(gateway)
    registry = tmp_path / "missing" / "registry.sqlite3"

    assert controller.devices(registry=registry) == []
    assert not registry.exists()
    assert not registry.parent.exists()


