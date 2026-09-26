"""Maintained Wire sampler for local WireGuard provisioning and inspection."""

from __future__ import annotations

import datetime as dt
import hashlib
import ipaddress
import json
import re
import secrets
import shutil
import sqlite3
import subprocess
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from gway.rendering import atomic_write_text


_TEMPLATE = Path(__file__).with_name("interface.conf")
_CLIENT_TEMPLATE = Path(__file__).with_name("client.conf")
_DEVICE_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
_PUBLIC_KEY_RE = re.compile(r"^[A-Za-z0-9+/]{43}=$")
_DEFAULT_REGISTER_HOST = "register.arthexis.com"
_DEFAULT_ENROLLMENT_PATH = "/v1/enroll"


def _utcnow():
    return dt.datetime.now(dt.timezone.utc)


def _stamp(value):
    return value.astimezone(dt.timezone.utc).isoformat(timespec="seconds")


def _token_hash(value):
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


class Registry:
    """Small durable Wire enrollment registry owned by the sampler."""

    def __init__(self, path, *, network="10.90.0.0/24", gateway_address="10.90.0.1"):
        self.path = Path(path)
        self.network = ipaddress.ip_network(network, strict=True)
        self.gateway_address = ipaddress.ip_address(gateway_address)
        if self.network.version != 4:
            raise ValueError("wire network must be IPv4")
        if self.gateway_address not in self.network:
            raise ValueError("wire gateway_address must belong to wire network")

    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS devices (
                device TEXT PRIMARY KEY,
                public_key TEXT NOT NULL UNIQUE,
                address TEXT NOT NULL UNIQUE,
                enabled INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS tokens (
                digest TEXT PRIMARY KEY,
                device TEXT,
                expires_at TEXT NOT NULL,
                consumed_at TEXT
            );
            """
        )
        return connection

    def list_devices(self, *, enabled=None):
        """Return enrolled devices in deterministic device order."""
        query = "SELECT * FROM devices"
        params = ()
        if enabled is not None:
            query += " WHERE enabled = ?"
            params = (1 if enabled else 0,)
        query += " ORDER BY device"
        with self.connect() as conn:
            return [dict(row) for row in conn.execute(query, params)]

    def get_device(self, device):
        """Return one enrolled device or None."""
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM devices WHERE device = ?", (_device(device),)
            ).fetchone()
        return None if row is None else dict(row)

    def revoke(self, device):
        """Disable one enrolled device idempotently."""
        device = _device(device)
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM devices WHERE device = ?", (device,)
            ).fetchone()
            if row is None:
                raise LookupError(f"unknown wire device: {device}")
            already = not bool(row["enabled"])
            if not already:
                conn.execute(
                    "UPDATE devices SET enabled = 0 WHERE device = ?", (device,)
                )
        return already

    def create_token(self, *, device=None, ttl=3600, token=None, now=None):
        if device is not None:
            _device(device)
        ttl = int(ttl)
        if not 1 <= ttl <= 7 * 24 * 3600:
            raise ValueError("wire token ttl must be between 1 and 604800 seconds")
        token = token or secrets.token_urlsafe(32)
        if len(token) < 20:
            raise ValueError("wire enrollment token must contain at least 20 characters")
        now = now or _utcnow()
        expires = now + dt.timedelta(seconds=ttl)
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO tokens (digest, device, expires_at, consumed_at) VALUES (?, ?, ?, NULL)",
                (_token_hash(token), device, _stamp(expires)),
            )
        return token, expires

    def _allocate(self, conn, *, externally_reserved=()):
        reserved = {
            ipaddress.ip_interface(row["address"]).ip
            for row in conn.execute("SELECT address FROM devices")
        }
        reserved.add(self.gateway_address)
        for value in externally_reserved:
            try:
                network = ipaddress.ip_network(str(value), strict=False)
            except ValueError:
                continue
            if network.version == 4:
                reserved.update(network.hosts() if network.prefixlen < 32 else [network.network_address])
        for candidate in self.network.hosts():
            if candidate not in reserved:
                return f"{candidate}/32"
        raise RuntimeError(f"no Wire addresses remain in {self.network}")

    def enroll(self, *, device, public_key, token, now=None, externally_reserved=()):
        device = _device(device)
        public_key = _public_key(public_key)
        now = now or _utcnow()
        digest = _token_hash(token)
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            token_row = conn.execute(
                "SELECT * FROM tokens WHERE digest = ?", (digest,)
            ).fetchone()
            if token_row is None or token_row["consumed_at"] is not None:
                raise PermissionError("invalid or already-used wire enrollment token")
            expires = dt.datetime.fromisoformat(token_row["expires_at"])
            if now >= expires:
                raise PermissionError("wire enrollment token expired")
            if token_row["device"] is not None and token_row["device"] != device:
                raise PermissionError("wire enrollment token is not valid for this device")

            existing = conn.execute(
                "SELECT * FROM devices WHERE device = ?", (device,)
            ).fetchone()
            created = False
            if existing is not None:
                if not existing["enabled"]:
                    raise PermissionError("wire device is revoked")
                if existing["public_key"] != public_key:
                    raise ValueError("wire device is already enrolled with another key")
                record = dict(existing)
            else:
                owner = conn.execute(
                    "SELECT device FROM devices WHERE public_key = ?", (public_key,)
                ).fetchone()
                if owner is not None:
                    raise ValueError("wire public key is already assigned to another device")
                address = self._allocate(conn, externally_reserved=externally_reserved)
                conn.execute(
                    "INSERT INTO devices (device, public_key, address, enabled) VALUES (?, ?, ?, 1)",
                    (device, public_key, address),
                )
                record = {
                    "device": device,
                    "public_key": public_key,
                    "address": address,
                    "enabled": 1,
                }
                created = True

            conn.execute(
                "UPDATE tokens SET consumed_at = ? WHERE digest = ?",
                (_stamp(now), digest),
            )
            conn.commit()
        return record, created


def _device(value):
    value = str(value).strip()
    if not _DEVICE_RE.fullmatch(value):
        raise ValueError("invalid wire device id")
    return value


def _public_key(value):
    value = str(value).strip()
    if not _PUBLIC_KEY_RE.fullmatch(value):
        raise ValueError("invalid WireGuard public key")
    return value



_MANAGED_BEGIN = "# BEGIN gway wire peer: "
_MANAGED_END = "# END gway wire peer: "


def _peer_allowed_ips(text):
    """Return AllowedIPs from every peer, including unmanaged peers."""
    section = None
    values = []
    for raw in str(text).splitlines():
        line = raw.strip()
        if line.startswith("[") and line.endswith("]"):
            section = line
            continue
        if section == "[Peer]" and line.startswith("AllowedIPs") and "=" in line:
            for item in line.split("=", 1)[1].split(","):
                item = item.strip()
                if item:
                    values.append(item)
    return values


def _strip_managed_peers(text):
    """Remove only sampler-owned peer blocks and preserve unrelated content."""
    output = []
    inside = False
    for raw in str(text).splitlines():
        line = raw.strip()
        if line.startswith(_MANAGED_BEGIN):
            if inside:
                raise ValueError("nested managed Wire peer block")
            inside = True
            continue
        if line.startswith(_MANAGED_END):
            if not inside:
                raise ValueError("orphan managed Wire peer block end")
            inside = False
            continue
        if not inside:
            output.append(raw)
    if inside:
        raise ValueError("unterminated managed Wire peer block")
    base = "\n".join(output).rstrip()
    return base + ("\n" if base else "")


def _managed_peer(device, public_key, address):
    return (
        f"{_MANAGED_BEGIN}{device}\n"
        "[Peer]\n"
        f"# Device = {device}\n"
        f"PublicKey = {public_key}\n"
        f"AllowedIPs = {address}\n"
        f"{_MANAGED_END}{device}\n"
    )


def _reconciled_config(current, devices):
    """Build desired server config while preserving all unmanaged content."""
    base = _strip_managed_peers(current)
    blocks = [
        _managed_peer(row["device"], row["public_key"], row["address"])
        for row in devices
        if row.get("enabled")
    ]
    if not blocks:
        return base
    return base.rstrip() + "\n\n" + "\n".join(blocks)


def _atomic_reconcile(path, desired):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, desired)
    return str(path)

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




def _json_handler(controller, settings):
    """Build the Watchtower enrollment HTTP handler."""

    class Handler(BaseHTTPRequestHandler):
        def _send(self, status, payload):
            data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)

        def do_GET(self):
            if self.path == "/health":
                self._send(
                    200,
                    {
                        "ok": True,
                        "service": "wire-enrollment",
                        "domain": settings["domain"],
                    },
                )
                return
            self._send(404, {"error": "not_found"})

        def do_POST(self):
            if self.path != _DEFAULT_ENROLLMENT_PATH:
                self._send(404, {"error": "not_found"})
                return
            try:
                length = int(self.headers.get("content-length", "0") or 0)
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                result = controller.accept_enrollment(
                    payload.get("device"),
                    public_key=payload.get("public_key"),
                    token=payload.get("token"),
                    registry=settings["registry"],
                    config=settings["config"],
                    server_public_key=settings["server_public_key"],
                    server_endpoint=settings["server_endpoint"],
                    network=settings["network"],
                    gateway_address=settings["gateway_address"],
                )
            except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
                self._send(400, {"error": "invalid_request", "message": str(error)})
                return
            except PermissionError as error:
                self._send(403, {"error": "enrollment_rejected", "message": str(error)})
                return
            except Exception as error:
                self._send(500, {"error": "enrollment_failed", "message": str(error)})
                return
            self._send(200, result)

        do_HEAD = do_GET

        def log_message(self, format, *args):
            return None

    return Handler


def build_enrollment_server(
    controller,
    *,
    host="127.0.0.1",
    port=8787,
    domain=_DEFAULT_REGISTER_HOST,
    registry,
    config,
    server_public_key,
    server_endpoint=None,
    network="10.90.0.0/24",
    gateway_address="10.90.0.1",
):
    """Build the local Watchtower Wire enrollment HTTP server."""
    endpoint = server_endpoint or f"{domain}:51820"
    settings = {
        "domain": str(domain).strip().lower(),
        "registry": str(registry),
        "config": str(config),
        "server_public_key": _public_key(server_public_key),
        "server_endpoint": str(endpoint).strip(),
        "network": str(network),
        "gateway_address": str(gateway_address),
    }
    return ThreadingHTTPServer(
        (str(host), int(port)),
        _json_handler(controller, settings),
    )

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

    def token(
        self,
        *,
        device=None,
        ttl=3600,
        registry=None,
        network="10.90.0.0/24",
        gateway_address="10.90.0.1",
        mutate=True,
    ):
        """Issue one expiring enrollment token from durable Wire state."""
        del mutate
        store = Registry(
            registry or self.gateway.data_root() / "wire" / "registry.sqlite3",
            network=network,
            gateway_address=gateway_address,
        )
        token, expires = store.create_token(device=device, ttl=ttl)
        return {
            "token": token,
            "device": device,
            "expires": _stamp(expires),
        }

    def enroll(
        self,
        device,
        *,
        public_key,
        token,
        private_key,
        server_public_key,
        server_endpoint,
        server_tunnel_ip="10.90.0.1",
        registry=None,
        server_config=None,
        network="10.90.0.0/24",
        gateway_address="10.90.0.1",
        to=None,
        sudo=False,
        rollback=None,
        mutate=True,
    ):
        """Enroll one client and render its WireGuard configuration."""
        del mutate
        store = Registry(
            registry or self.gateway.data_root() / "wire" / "registry.sqlite3",
            network=network,
            gateway_address=gateway_address,
        )
        reserved = ()
        if server_config is not None and Path(server_config).is_file():
            reserved = _peer_allowed_ips(Path(server_config).read_text(encoding="utf-8"))
        record, created = store.enroll(
            device=device,
            public_key=public_key,
            token=token,
            externally_reserved=reserved,
        )
        private_key = str(private_key).strip()
        if not private_key:
            raise ValueError("wire private key must be non-empty")
        server_public_key = _public_key(server_public_key)
        endpoint = str(server_endpoint).strip()
        if not endpoint:
            raise ValueError("wire server_endpoint must be non-empty")

        destination = (
            Path(to)
            if to is not None
            else self.gateway.data_root() / "wire" / "clients" / _device(device) / "wireguard.conf"
        )
        values = {
            "wire_client_address": record["address"],
            "wire_client_private_key": private_key,
            "wire_server_public_key": server_public_key,
            "wire_server_endpoint": endpoint,
            "wire_server_tunnel_ip": str(server_tunnel_ip).strip(),
        }
        with _context(self.gateway, values):
            rendered = self.gateway.render(
                str(_CLIENT_TEMPLATE),
                to=str(destination),
                sudo=sudo,
                rollback=rollback,
            )
        return {
            "device": record["device"],
            "address": record["address"],
            "public_key": record["public_key"],
            "config": str(rendered),
            "created": created,
        }

    def accept_enrollment(
        self,
        device,
        *,
        public_key,
        token,
        registry,
        config,
        server_public_key,
        server_endpoint,
        network="10.90.0.0/24",
        gateway_address="10.90.0.1",
        mutate=True,
    ):
        """Accept one authenticated client and reconcile its server peer."""
        del mutate
        store = Registry(
            registry,
            network=network,
            gateway_address=gateway_address,
        )
        reserved = ()
        config_path = Path(config)
        if config_path.is_file():
            reserved = _peer_allowed_ips(config_path.read_text(encoding="utf-8"))
        record, created = store.enroll(
            device=device,
            public_key=public_key,
            token=token,
            externally_reserved=reserved,
        )
        reconciled = self.sync(
            registry=store.path,
            config=config_path,
            network=network,
            gateway_address=gateway_address,
        )
        return {
            "device": record["device"],
            "address": record["address"],
            "public_key": record["public_key"],
            "server_public_key": _public_key(server_public_key),
            "server_endpoint": str(server_endpoint).strip(),
            "server_tunnel_ip": str(gateway_address),
            "created": created,
            "peer_changed": reconciled["changed"],
        }

    def serve_enrollment(
        self,
        host="127.0.0.1",
        port=8787,
        *,
        domain=_DEFAULT_REGISTER_HOST,
        registry=None,
        config="/etc/wireguard/gway.conf",
        server_public_key,
        server_endpoint=None,
        network="10.90.0.0/24",
        gateway_address="10.90.0.1",
        mutate=True,
    ):
        """Serve the Watchtower enrollment API until the service stops."""
        del mutate
        server = build_enrollment_server(
            self,
            host=host,
            port=port,
            domain=domain,
            registry=registry or self.gateway.data_root() / "wire" / "registry.sqlite3",
            config=config,
            server_public_key=server_public_key,
            server_endpoint=server_endpoint,
            network=network,
            gateway_address=gateway_address,
        )
        try:
            return server.serve_forever()
        finally:
            server.server_close()

    @staticmethod
    def _enrollment_url(domain):
        domain = str(domain).strip().lower().rstrip(".")
        if not domain:
            raise ValueError("wire enrollment domain must be non-empty")
        return f"https://{domain}{_DEFAULT_ENROLLMENT_PATH}"

    def server_check(
        self,
        *,
        domain=_DEFAULT_REGISTER_HOST,
        interface="gway",
        public_address=None,
        dns_backend="godaddy",
        dns_zone="arthexis.com",
        registry=None,
        mutate=False,
    ):
        """Check central Wire server readiness without changing host state."""
        del mutate
        local = self.check(interface=interface)
        store_path = Path(
            registry or self.gateway.data_root() / "wire" / "registry.sqlite3"
        )
        registry_ready = store_path.is_file()
        dns_ready = None
        if public_address is not None:
            dns_ready = self.gateway._dns_controller.ready(
                domain,
                type="A",
                value=public_address,
                backend=dns_backend,
                zone=dns_zone,
            )
        checks = {
            "wireguard": local["ok"],
            "registry": registry_ready,
            "dns": dns_ready,
        }
        required = [checks["wireguard"], checks["registry"]]
        if dns_ready is not None:
            required.append(dns_ready)
        return {
            "role": "watchtower",
            "central": True,
            "domain": str(domain).strip().lower(),
            "enrollment_url": self._enrollment_url(domain),
            "interface": interface,
            "checks": checks,
            "ready": all(required),
        }

    def deploy_server(
        self,
        *,
        domain=_DEFAULT_REGISTER_HOST,
        interface="gway",
        address="10.90.0.1/24",
        private_key,
        listen_port=51820,
        registry=None,
        config=None,
        public_address=None,
        dns_backend="godaddy",
        dns_zone="arthexis.com",
        sudo=False,
        rollback="wire-watchtower",
        mutate=True,
    ):
        """Converge this host into the central Watchtower Wire server role."""
        del mutate
        store_path = Path(
            registry or self.gateway.data_root() / "wire" / "registry.sqlite3"
        )
        # Opening the registry initializes durable central enrollment state.
        Registry(store_path).connect().close()

        destination = (
            Path(config)
            if config is not None
            else Path("/etc/wireguard") / f"{interface}.conf"
        )
        provisioned = self.provision(
            interface,
            address=address,
            private_key=private_key,
            listen_port=listen_port,
            to=destination,
            sudo=sudo,
            rollback=rollback,
        )
        readiness = self.server_check(
            domain=domain,
            interface=interface,
            public_address=public_address,
            dns_backend=dns_backend,
            dns_zone=dns_zone,
            registry=store_path,
        )
        return {
            "role": "watchtower",
            "central": True,
            "domain": str(domain).strip().lower(),
            "enrollment_url": self._enrollment_url(domain),
            "registry": str(store_path),
            "config": provisioned["config"],
            "interface": interface,
            "readiness": readiness,
        }

    def devices(
        self,
        *,
        registry=None,
        network="10.90.0.0/24",
        gateway_address="10.90.0.1",
        mutate=False,
    ):
        """List enrolled Wire devices without changing state."""
        del mutate
        store = Registry(
            registry or self.gateway.data_root() / "wire" / "registry.sqlite3",
            network=network,
            gateway_address=gateway_address,
        )
        return store.list_devices()

    def sync(
        self,
        *,
        registry=None,
        config="/etc/wireguard/gway.conf",
        network="10.90.0.0/24",
        gateway_address="10.90.0.1",
        mutate=True,
    ):
        """Reconcile sampler-managed peers while preserving unmanaged peers."""
        del mutate
        store = Registry(
            registry or self.gateway.data_root() / "wire" / "registry.sqlite3",
            network=network,
            gateway_address=gateway_address,
        )
        path = Path(config)
        if not path.is_file():
            raise FileNotFoundError(f"WireGuard config does not exist: {path}")
        current = path.read_text(encoding="utf-8")
        desired = _reconciled_config(current, store.list_devices(enabled=True))
        changed = desired != current
        if changed:
            _atomic_reconcile(path, desired)
        return {
            "config": str(path),
            "changed": changed,
            "devices": [
                row["device"] for row in store.list_devices(enabled=True)
            ],
        }

    def revoke(
        self,
        device,
        *,
        registry=None,
        config="/etc/wireguard/gway.conf",
        network="10.90.0.0/24",
        gateway_address="10.90.0.1",
        mutate=True,
    ):
        """Revoke one device and remove only its sampler-owned peer state."""
        del mutate
        store = Registry(
            registry or self.gateway.data_root() / "wire" / "registry.sqlite3",
            network=network,
            gateway_address=gateway_address,
        )
        already = store.revoke(device)
        sync = self.sync(
            registry=store.path,
            config=config,
            network=network,
            gateway_address=gateway_address,
        )
        return {
            "device": _device(device),
            "revoked": True,
            "already_revoked": already,
            "config_changed": sync["changed"],
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
    token = gateway.wrap(
        "wire.server.token",
        controller.token,
        op="token",
        sub="server",
    )
    enroll = gateway.wrap(
        "wire.client.enroll",
        controller.enroll,
        op="enroll",
        sub="client",
    )
    enrollment_serve = gateway.wrap(
        "wire.server.serve",
        controller.serve_enrollment,
        op="serve",
        sub="server",
    )
    server_check = gateway.wrap(
        "wire.server.check",
        controller.server_check,
        op="check",
        sub="server",
    )
    server_deploy = gateway.wrap(
        "wire.server.deploy",
        controller.deploy_server,
        op="deploy",
        sub="server",
    )
    devices = gateway.wrap(
        "wire.server.devices",
        controller.devices,
        op="devices",
        sub="server",
    )
    revoke = gateway.wrap(
        "wire.server.revoke",
        controller.revoke,
        op="revoke",
        sub="server",
    )
    sync = gateway.wrap("wire.sync", controller.sync, op="sync", sub="wire")
    server_sync = gateway.wrap(
        "wire.server.sync",
        controller.sync,
        op="sync",
        sub="server",
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
        "wireguard.server.token": token,
        "wg.server.token": token,
        "wireguard.client.enroll": enroll,
        "wg.client.enroll": enroll,
        "wireguard.server.serve": enrollment_serve,
        "wg.server.serve": enrollment_serve,
        "wireguard.server.check": server_check,
        "wg.server.check": server_check,
        "wireguard.server.deploy": server_deploy,
        "wg.server.deploy": server_deploy,
        "wireguard.server.devices": devices,
        "wg.server.devices": devices,
        "wireguard.server.revoke": revoke,
        "wg.server.revoke": revoke,
        "wireguard.sync": sync,
        "wg.sync": sync,
        "wireguard.server.sync": server_sync,
        "wg.server.sync": server_sync,
        "wireguard.client.status": client_status,
        "wg.client.status": client_status,
        "wireguard.server.status": server_status,
        "wg.server.status": server_status,
    }.items():
        gateway.ops.register_alias(alias, operation)

    from gway.service.model import Service

    launchable = gateway.launchables["wire.server.serve"]
    service = Service(
        project="gway",
        name="wire-enroll",
        root=Path(__file__).resolve().parents[2],
        launchable=launchable,
        description="Watchtower Wire client enrollment service",
        working_directory="{project}",
        state_root=gateway.data_root() / "services",
    )
    gateway._service_presets[service.identity] = service

    return controller


__all__ = ["Controller", "Registry", "build_enrollment_server", "register"]
