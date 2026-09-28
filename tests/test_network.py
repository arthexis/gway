import json
from pathlib import Path

import pytest

from gway import Gateway
from gway.network import Controller, RedirectUnavailable


class Result:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class FakeGateway:
    def __init__(self, root: Path):
        self.root = root

    def data_root(self):
        return self.root


def test_network_operations_are_registered():
    gateway = Gateway()

    assert gateway.ops.resolve("network.redirect") is not None
    assert gateway.ops.resolve("network.remove") is not None
    assert gateway.ops.resolve("network.status") is not None
    assert gateway.ops.resolve("network.available") is not None
    assert gateway.ops.resolve("network.redirect").mutates is True
    assert gateway.ops.resolve("network.remove").mutates is True
    assert gateway.ops.resolve("network.status").mutates is False
    assert gateway.ops.resolve("network.available").mutates is False


def test_network_available_is_non_mutating(tmp_path):
    controller = Controller(
        FakeGateway(tmp_path),
        which=lambda name: "/usr/sbin/nft" if name == "nft" else None,
    )

    assert controller.available() == {
        "available": True,
        "backend": "nftables",
        "strategy": "destination-redirect",
    }


def test_network_redirect_reports_missing_nft(tmp_path):
    controller = Controller(FakeGateway(tmp_path), which=lambda _name: None)

    with pytest.raises(RedirectUnavailable, match="requires nftables"):
        controller.redirect("eth0", "198.51.100.40", 9000, target_port=9000)


def test_network_redirect_creates_owned_ipv4_table(monkeypatch, tmp_path):
    calls = []

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        return Result()

    controller = Controller(
        FakeGateway(tmp_path),
        runner=runner,
        which=lambda name: "/usr/sbin/nft" if name == "nft" else None,
    )
    monkeypatch.setattr(
        "gway.network.uuid.uuid4",
        lambda: type("UUID", (), {"hex": "abcdef1234567890"})(),
    )

    result = controller.redirect(
        "eth0",
        "198.51.100.40",
        9000,
        target="127.0.0.1",
        target_port=9000,
    )

    assert result["id"] == "abcdef123456"
    assert result["table"] == "gway_capture_abcdef123456"
    assert result["active"] is True
    assert calls[0][0] == ["/usr/sbin/nft", "-f", "-"]
    script = calls[0][1]["input"]
    assert "add table ip gway_capture_abcdef123456" in script
    assert 'iifname "eth0"' in script
    assert "ip daddr 198.51.100.40" in script
    assert "tcp dport 9000 redirect to :9000" in script

    state = json.loads(
        (
            tmp_path
            / "network"
            / "redirects"
            / "abcdef123456.json"
        ).read_text(encoding="utf-8")
    )
    assert state["destination"] == "198.51.100.40"
    assert state["active"] is True


def test_network_redirect_uses_ip6_family(monkeypatch, tmp_path):
    calls = []

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        return Result()

    controller = Controller(
        FakeGateway(tmp_path),
        runner=runner,
        which=lambda _name: "/usr/sbin/nft",
    )
    monkeypatch.setattr(
        "gway.network.uuid.uuid4",
        lambda: type("UUID", (), {"hex": "0123456789abcdef"})(),
    )

    result = controller.redirect(
        "eth0",
        "2001:db8::40",
        443,
        target="::1",
        target_port=9000,
    )

    assert result["family"] == "ip6"
    script = calls[0][1]["input"]
    assert "add table ip6 gway_capture_0123456789ab" in script
    assert "ip6 daddr 2001:db8::40" in script


def test_network_redirect_rejects_non_loopback_target(tmp_path):
    controller = Controller(
        FakeGateway(tmp_path),
        which=lambda _name: "/usr/sbin/nft",
    )

    with pytest.raises(ValueError, match="loopback"):
        controller.redirect(
            "eth0",
            "198.51.100.40",
            9000,
            target="192.0.2.10",
            target_port=9000,
        )


def test_network_remove_is_idempotent(monkeypatch, tmp_path):
    calls = []
    exists = {"value": True}

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        if command[1:3] == ["list", "table"]:
            return Result(returncode=0 if exists["value"] else 1)
        if command[1:3] == ["delete", "table"]:
            exists["value"] = False
        return Result()

    controller = Controller(
        FakeGateway(tmp_path),
        runner=runner,
        which=lambda _name: "/usr/sbin/nft",
    )
    monkeypatch.setattr(
        "gway.network.uuid.uuid4",
        lambda: type("UUID", (), {"hex": "abcdef1234567890"})(),
    )
    created = controller.redirect(
        "eth0",
        "198.51.100.40",
        9000,
        target_port=9000,
    )

    first = controller.remove(created["id"])
    second = controller.remove(created["id"])

    assert first["changed"] is True
    assert first["active"] is False
    assert second["changed"] is False
    assert second["active"] is False


def test_redirect_apply_failure_does_not_leave_owned_state(monkeypatch, tmp_path):
    def runner(command, **kwargs):
        if command[1:3] == ["-f", "-"]:
            return Result(returncode=1, stderr="permission denied")
        return Result()

    controller = Controller(
        FakeGateway(tmp_path),
        runner=runner,
        which=lambda _name: "/usr/sbin/nft",
    )
    monkeypatch.setattr(
        "gway.network.uuid.uuid4",
        lambda: type("UUID", (), {"hex": "abcdef1234567890"})(),
    )

    with pytest.raises(RuntimeError, match="permission denied"):
        controller.redirect("eth0", "198.51.100.40", 9000, target_port=9000)

    assert not (
        tmp_path / "network" / "redirects" / "abcdef123456.json"
    ).exists()



def test_network_redirect_uses_standard_sudo_identity(monkeypatch, tmp_path):
    calls = []

    def runner(command, **kwargs):
        calls.append(command)
        return Result()

    controller = Controller(
        FakeGateway(tmp_path),
        runner=runner,
        which=lambda name: "/usr/sbin/nft" if name == "nft" else None,
    )
    monkeypatch.setattr(
        "gway.network.uuid.uuid4",
        lambda: type("UUID", (), {"hex": "abcdef1234567890"})(),
    )

    controller.redirect(
        "eth0",
        "198.51.100.40",
        9000,
        target_port=9000,
        sudo=True,
    )

    assert calls[0][:2] == ["sudo", "/usr/sbin/nft"]
