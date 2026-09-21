import pytest

from gway import Gateway
from gway.install.identity import RuntimeIdentity


def test_gateway_snapshots_running_identity_once(monkeypatch):
    initial = RuntimeIdentity(
        resolved_revision="abc123",
        fingerprint="fp-1",
        scope="user",
    )
    later = RuntimeIdentity(
        resolved_revision="def456",
        fingerprint="fp-2",
        scope="user",
    )
    calls = []

    def identify():
        calls.append(len(calls))
        return initial if len(calls) == 1 else later

    monkeypatch.setattr("gway.install.identity.running_gway_identity", identify)

    gateway = Gateway()

    assert gateway.gway_identity == initial
    assert calls == [0]

    # The startup snapshot is deliberately stable for the life of this runtime.
    assert gateway.gway_identity == initial
    assert calls == [0]


def test_gateway_identity_is_none_for_unmanaged_runtime(monkeypatch):
    monkeypatch.setattr(
        "gway.install.identity.running_gway_identity",
        lambda: None,
    )

    gateway = Gateway()

    assert gateway.gway_identity is None
