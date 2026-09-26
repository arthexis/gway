"""Maintained Wire sampler for local WireGuard provisioning and inspection."""

from __future__ import annotations

import shutil
import subprocess
from contextlib import contextmanager
from pathlib import Path


_TEMPLATE = Path(__file__).with_name("interface.conf")


def _run(argv):
    return subprocess.run(argv, check=False, capture_output=True, text=True)


def _wg_values(output):
    values = {
        "public_key": None,
        "listen_port": None,
        "peer_count": 0,
    }
    for line in str(output).splitlines():
        text = line.strip()
        if text.startswith("public key:"):
            values["public_key"] = text.partition(":")[2].strip() or None
        elif text.startswith("listening port:"):
            values["listen_port"] = text.partition(":")[2].strip() or None
        elif text.startswith("peer:"):
            values["peer_count"] += 1
    return values


@contextmanager
def _context(runtime, values):
    missing = object()
    before = {name: runtime.context.get(name, missing) for name in values}
    runtime.context.update(values)
    try:
        yield
    finally:
        for name, value in before.items():
            if value is missing:
                runtime.context.pop(name, None)
            else:
                runtime.context[name] = value


class Controller:
    """Expose local WireGuard operations through the Wire command family."""

    def __init__(self, gateway, *, runner=None, which=None):
        self.gateway = gateway
        self.runner = runner or _run
        self.which = which or shutil.which

    def status(self, interface="gway", debug=False, mutate=False):
        """Return local WireGuard interface status without changing host state."""
        del mutate
        interface = str(interface).strip()
        if not interface:
            raise ValueError("wire interface must be non-empty")

        wg = self.which("wg")
        if wg is None:
            return {
                "interface": interface,
                "configured": False,
                "running": False,
                "reason": "wg executable not found",
            }

        result = self.runner([wg, "show", interface])
        if result.returncode != 0:
            return {
                "interface": interface,
                "configured": False,
                "running": False,
                "reason": result.stderr.strip() or result.stdout.strip() or "interface not found",
            }

        parsed = _wg_values(result.stdout)
        response = {
            "interface": interface,
            "configured": True,
            "running": True,
            "public_key": parsed["public_key"],
            "listen_port": parsed["listen_port"],
            "peer_count": parsed["peer_count"],
        }
        if debug:
            response["detail"] = result.stdout.strip()
        return response

    def check(self, interface="gway", mutate=False):
        """Return a read-only local readiness result for one WireGuard interface."""
        del mutate
        status = self.status(interface=interface)
        return {
            "interface": status["interface"],
            "ok": bool(status.get("configured") and status.get("running")),
            "status": status,
        }

    def provision(
        self,
        interface="gway",
        *,
        address,
        private_key,
        listen_port=51820,
        to=None,
        sudo=False,
        rollback=None,
        mutate=True,
    ):
        """Render one local WireGuard interface configuration atomically."""
        del mutate
        interface = str(interface).strip()
        if not interface:
            raise ValueError("wire interface must be non-empty")
        address = str(address).strip()
        private_key = str(private_key).strip()
        if not address:
            raise ValueError("wire address must be non-empty")
        if not private_key:
            raise ValueError("wire private key must be non-empty")
        port = int(listen_port)
        if not 1 <= port <= 65535:
            raise ValueError("wire listen_port must be between 1 and 65535")

        destination = Path(to) if to is not None else Path("/etc/wireguard") / f"{interface}.conf"
        values = {
            "wire_interface": interface,
            "wire_address": address,
            "wire_private_key": private_key,
            "wire_listen_port": port,
        }
        with _context(self.gateway, values):
            rendered = self.gateway.render(
                str(_TEMPLATE),
                to=str(destination),
                sudo=sudo,
                rollback=rollback,
            )

        return {
            "interface": interface,
            "address": address,
            "listen_port": port,
            "config": str(rendered),
        }


def register(gateway, *, runner=None, which=None):
    """Register the local Wire sampler surface lazily on one Gateway."""
    controller = Controller(gateway, runner=runner, which=which)
    gateway._wire_controller = controller

    status = gateway.wrap("wire.status", controller.status, op="status", sub="wire")
    check = gateway.wrap("wire.check", controller.check, op="check", sub="wire")
    provision = gateway.wrap(
        "wire.provision",
        controller.provision,
        op="provision",
        sub="wire",
    )
    client_status = gateway.wrap(
        "wire.client.status",
        controller.status,
        op="status",
        sub="client",
    )
    server_status = gateway.wrap(
        "wire.server.status",
        controller.status,
        op="status",
        sub="server",
    )

    for alias, operation in {
        "wireguard.status": status,
        "wg.status": status,
        "wireguard.check": check,
        "wg.check": check,
        "wireguard.provision": provision,
        "wg.provision": provision,
        "wireguard.client.status": client_status,
        "wg.client.status": client_status,
        "wireguard.server.status": server_status,
        "wg.server.status": server_status,
    }.items():
        gateway.ops.register_alias(alias, operation)

    return controller


__all__ = ["Controller", "register"]
