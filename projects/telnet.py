"""Telnet helpers for Gateway projects."""

from __future__ import annotations

import telnetlib
from typing import Any


def connectfunction(*, host: str, port: int = 23, timeout: float | None = 10.0) -> dict[str, Any]:
    """Open a Telnet connection to ``host`` and ``port``.

    Parameters
    ----------
    host:
        Hostname or IP address to connect to. Required.
    port:
        Telnet port number. Defaults to ``23``.
    timeout:
        Optional timeout in seconds passed to :class:`telnetlib.Telnet`.

    Returns a payload that includes the live ``telnetlib.Telnet`` connection so
    it can be reused by follow-up commands.
    """

    if not host:
        raise ValueError("A host must be provided to open a Telnet connection")

    connection = telnetlib.Telnet(host=host, port=int(port), timeout=timeout)
    return {
        "connection": connection,
        "host": host,
        "port": int(port),
        "timeout": timeout,
        "status": "connected",
    }
