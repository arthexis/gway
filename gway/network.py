"""Temporary host-network redirection owned by Gway."""

from __future__ import annotations

import ipaddress
import json
import re
import shutil
import subprocess
import uuid
from pathlib import Path


_TABLE_PREFIX = "gway_capture_"
_HANDLE_RE = re.compile(r"^[a-f0-9]{12}$")


class RedirectUnavailable(RuntimeError):
    """Raised when the host cannot provide temporary network redirection."""


class Controller:
    """Own narrowly scoped, reversible local network redirects."""

    def __init__(self, gateway, *, runner=None, which=None):
        self.gateway = gateway
        self.runner = runner or subprocess.run
        self.which = which or shutil.which

    def _state_root(self) -> Path:
        return Path(self.gateway.data_root()) / "network" / "redirects"

    def _nft(self) -> str:
        executable = self.which("nft")
        if not executable:
            raise RedirectUnavailable(
                "Network redirect requires nftables (nft). "
                "Provision the host network capability before using automatic capture."
            )
        return executable

    @staticmethod
    def _port(value, name: str) -> int:
        port = int(value)
        if not 1 <= port <= 65535:
            raise ValueError(f"{name} must be between 1 and 65535")
        return port

    @staticmethod
    def _interface(value) -> str:
        interface = str(value).strip()
        if not interface:
            raise ValueError("interface must be non-empty")
        if any(character.isspace() for character in interface):
            raise ValueError("interface may not contain whitespace")
        return interface

    @staticmethod
    def _local_target(value: str, *, family: int) -> str:
        address = ipaddress.ip_address(str(value).strip())
        if address.version != family:
            raise ValueError("target address family must match destination")
        if not address.is_loopback:
            raise ValueError(
                "the first redirect backend supports only a loopback local target"
            )
        return str(address)

    def available(self, *, mutate=False) -> dict[str, object]:
        """Report whether the nftables redirect backend is available."""
        del mutate
        executable = self.which("nft")
        return {
            "available": executable is not None,
            "backend": "nftables" if executable is not None else None,
            "strategy": "destination-redirect" if executable is not None else None,
        }

    def _run(self, *arguments: str, input_text: str | None = None):
        result = self.runner(
            [self._nft(), *arguments],
            input=input_text,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(f"nftables redirect failed: {detail or result.returncode}")
        return result

    def _table_exists(self, family: str, table: str) -> bool:
        result = self.runner(
            [self._nft(), "list", "table", family, table],
            text=True,
            capture_output=True,
            check=False,
        )
        return result.returncode == 0

    def redirect(
        self,
        interface,
        destination,
        port,
        *,
        target="127.0.0.1",
        target_port=None,
        mutate=True,
    ) -> dict[str, object]:
        """Redirect matching inbound TCP traffic to a local listener.

        The first backend uses one dedicated nftables table per redirect so cleanup
        never needs to inspect or modify unrelated firewall rules.
        """
        del mutate
        interface = self._interface(interface)
        address = ipaddress.ip_address(str(destination).strip())
        destination_port = self._port(port, "port")
        local_port = self._port(
            destination_port if target_port is None else target_port,
            "target_port",
        )
        local_target = self._local_target(str(target), family=address.version)
        family = "ip" if address.version == 4 else "ip6"
        address_keyword = "ip" if address.version == 4 else "ip6"

        handle = uuid.uuid4().hex[:12]
        table = f"{_TABLE_PREFIX}{handle}"
        script = "\n".join(
            [
                f"add table {family} {table}",
                (
                    f"add chain {family} {table} prerouting "
                    "{ type nat hook prerouting priority dstnat; policy accept; }"
                ),
                (
                    f'add rule {family} {table} prerouting iifname "{interface}" '
                    f"{address_keyword} daddr {address} tcp dport {destination_port} "
                    f"redirect to :{local_port}"
                ),
                "",
            ]
        )
        self._run("-f", "-", input_text=script)

        record = {
            "id": handle,
            "backend": "nftables",
            "strategy": "destination-redirect",
            "family": family,
            "table": table,
            "interface": interface,
            "destination": str(address),
            "port": destination_port,
            "target": local_target,
            "target_port": local_port,
            "active": True,
        }
        root = self._state_root()
        root.mkdir(parents=True, exist_ok=True)
        (root / f"{handle}.json").write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return record

    def remove(self, id, *, mutate=True) -> dict[str, object]:
        """Remove one owned redirect; repeated removal is safe."""
        del mutate
        handle = str(id).strip().lower()
        if not _HANDLE_RE.fullmatch(handle):
            raise ValueError("redirect id must be a 12-character hexadecimal handle")

        path = self._state_root() / f"{handle}.json"
        if not path.is_file():
            return {"id": handle, "active": False, "changed": False}

        record = json.loads(path.read_text(encoding="utf-8"))
        family = str(record["family"])
        table = str(record["table"])
        changed = False
        if self._table_exists(family, table):
            self._run("delete", "table", family, table)
            changed = True

        record["active"] = False
        record["changed"] = changed
        path.write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return record

    def status(self, id, *, mutate=False) -> dict[str, object]:
        """Inspect one owned redirect without changing host state."""
        del mutate
        handle = str(id).strip().lower()
        if not _HANDLE_RE.fullmatch(handle):
            raise ValueError("redirect id must be a 12-character hexadecimal handle")
        path = self._state_root() / f"{handle}.json"
        if not path.is_file():
            return {"id": handle, "active": False, "known": False}

        record = json.loads(path.read_text(encoding="utf-8"))
        record["known"] = True
        record["active"] = self._table_exists(
            str(record["family"]),
            str(record["table"]),
        )
        return record
