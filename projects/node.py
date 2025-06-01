# projects/node.py

import os
import uuid
import secrets
import platform
import subprocess
import requests
import platform, socket, json
from gway import gw


def report(**kwargs):
    """Generate a system report with platform info and recent logs."""
    try:
        log_path = gw.resource("logs", "gway.log")
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            last_lines = f.readlines()[-100:]
    except Exception as e:
        last_lines = [f"<Could not read log file: {e}>"]

    system_info = {
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "kwargs": kwargs
    }

    return (
        "System Info:\n" +
        json.dumps(system_info, indent=2) +
        "\n\nRecent Log Lines:\n" +
        "".join(last_lines)
    )


def register(
    server: str,
    node_key: str,
    start: str = None,
    end: str = None,
    credits: int = None,
    role: str = "ADMIN",
):
    """
    Register this node with the given server's /register endpoint.

    Generates a secret_key, stores it locally, and sends it (along with any
    optional 'start', 'end', 'credits', and 'role' fields) to the server.

    Args:
        server (str): Base URL of the server (including port).
        node_key (str): Unique identifier for this node.
        start (str, optional): ISO date string when this node becomes active.
                               Defaults to now if omitted.
        end (str, optional): ISO date string when this node expires.
        credits (int, optional): Number of credits to grant.
        role (str, optional): Role for this node (e.g., 'ADMIN', 'NODE'). Defaults to 'ADMIN'.
    """
    # Validate required arguments
    if not server or not node_key:
        raise ValueError("Both 'server' and 'node_key' parameters are required.")

    # Generate a new secret_key and save it locally (overwrites if it already exists).
    secret_key = secrets.token_urlsafe(32)
    secret_path = gw.resource("work", f"node.{node_key}.secret")
    os.makedirs(os.path.dirname(secret_path), exist_ok=True)
    with open(secret_path, "w", encoding="utf-8") as f:
        f.write(secret_key)

    # Build payload including all provided fields
    url = f"{server.rstrip('/')}/register"
    payload = {
        "node_key": node_key,
        "secret_key": secret_key,
    }
    if start:
        payload["start"] = start
    if end:
        payload["end"] = end
    if credits is not None:
        payload["credits"] = credits
    if role:
        payload["role"] = role.upper()

    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        return f"Failed to register node with server: {e}"


def check(server: str, node_key: str) -> str:
    """
    Check registration status for this node.

    Reads the locally‐stored secret_key, then POSTs {node_key, secret_key} to
    the server's /register endpoint. The server will respond with text indicating
    "approved", "denied", or "pending."

    Args:
        server (str): Base URL of the server (including port).
        node_key (str): Unique identifier for this node (must have run register()).

    Returns:
        str: The raw text response from the server, which will say either:
             - "Node <node_key> approved."
             - "Node <node_key> has been denied."
             - "Node <node_key> registration is pending."
    """
    if not server or not node_key:
        raise ValueError("Both 'server' and 'node_key' parameters are required.")

    secret_path = gw.resource("work", f"node.{node_key}.secret")
    if not os.path.isfile(secret_path):
        raise FileNotFoundError(
            f"Cannot find secret file at {secret_path}. Have you run register()?"
        )

    with open(secret_path, "r", encoding="utf-8") as f:
        secret_key = f.read().strip()

    url = f"{server.rstrip('/')}/register"
    payload = {
        "node_key": node_key,
        "secret_key": secret_key,
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        return f"Failed to check registration status: {e}"


def identify() -> str:
    """
    Returns a unique identifier for this system.
    
    Tries platform-specific hardware serials and falls back to a UUID based on MAC address.
    """
    system = platform.system()

    if system == "Linux":
        # Try Raspberry Pi CPU serial
        try:
            with open("/proc/cpuinfo", "r") as f:
                for line in f:
                    if line.startswith("Serial"):
                        return line.strip().split(":")[1].strip()
        except Exception:
            pass

        # Fallback to machine-id
        try:
            with open("/etc/machine-id", "r") as f:
                return f.read().strip()
        except Exception:
            pass

    elif system == "Windows":
        try:
            output = subprocess.check_output(["wmic", "csproduct", "get", "uuid"], stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
            lines = output.decode().splitlines()
            for line in lines:
                line = line.strip()
                if line and line != "UUID":
                    return line
        except Exception:
            pass

    # Final fallback: UUID based on MAC + hostname
    try:
        mac = uuid.getnode()
        host = platform.node()
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{mac}-{host}"))
    except Exception:
        return "UNKNOWN"
