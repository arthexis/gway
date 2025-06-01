# projects/node.py

import os
import uuid
import secrets
import platform
import subprocess
import requests
import socket
import json
from gway import gw


def register(
        *,
        node_key: str = None,
        server: str = None,
        start: str = None,
        end: str = None,
        credits: int = None,
        role: str = "ADMIN",
        message: str = None,
        manual: bool = False,
        endpoint: str = "/gway/register",
    ):
    """
    Register this node with the given server's register endpoint.

    Generates a secret_key (or reuses existing one), stores it locally in identity.cdv,
    and sends it (along with optional metadata) to the server.
    """
    if not endpoint.startswith('/'): 
        endpoint = "/" + endpoint
    
    if not node_key:
        node_key = identify()

    if not server:
        server = os.environ.get("SERVER_URL")

    if manual and (not server):
        print("Error: cannot run in manual mode—no 'server' specified and $SERVER_URL is unset.")
        return "Manual registration aborted (missing server)."

    if not server or not node_key:
        raise ValueError("Both 'server' (or env['SERVER_URL']) and 'node_key' are required.")

    # Attempt to reuse secret_key from identity.cdv
    existing = gw.cdv.find("work", "identity", node_key, **{"0": r"^sk=(.*)"})
    if isinstance(existing, dict) and "secret_key" in existing:
        secret_key = existing["secret_key"]
    elif isinstance(existing, str):
        secret_key = existing
    else:
        secret_key = secrets.token_urlsafe(32)
        identity_record = {"sk": secret_key}
        if role:
            identity_record["role"] = role.upper()
        if start:
            identity_record["start"] = start
        if end:
            identity_record["end"] = end
        if credits is not None:
            identity_record["credits"] = credits
        gw.cdv.store("work", "identity", node_key, value=identity_record)

    url = f"{server.rstrip('/')}{endpoint}"
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
    if message:
        payload["message"] = message

    if manual:
        print(f"[Manual Registration Required]")
        print(f"Visit this URL: {url}")
        print("Submit the following JSON payload:")
        print(json.dumps(payload, indent=2))
        return "Manual registration output printed."

    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        return f"Failed to register node with server: {e}"


...


def report(**kwargs):
    """Generate a system report with platform info and recent logs."""

    # Include the unique node identifier
    node_id = identify()

    try:
        log_path = gw.resource("logs", "gway.log")
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            last_lines = f.readlines()[-100:]
    except Exception as e:
        last_lines = [f"<Could not read log file: {e}>"]

    system_info = {
        "node_id": node_id,
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


def check(server: str, node_key: str, endpoint: str = "/gway/register") -> str:
    """
    Check registration status for this node.

    Reads the locally‐stored secret_key, then POSTs {node_key, secret_key} to
    the server's register endpoint. The server will respond with text indicating
    "approved", "denied", or "pending."

    Only returns cleanly if the server explicitly indicates approval; otherwise, raises
    or returns an error message.

    Args:
        server (str): Base URL of the server (including port).
        node_key (str): Unique identifier for this node (must have run register()).

    Returns:
        str: If approved, returns "<Server response containing 'approved'>".
             If denied or pending, returns "Node not approved: <server-text>".
    """
    if not endpoint.startswith('/'): 
        endpoint = "/" + endpoint

    if not server or not node_key:
        raise ValueError("Both 'server' and 'node_key' parameters are required.")

    secret_path = gw.resource("work", f"node.{node_key}.secret")
    if not os.path.isfile(secret_path):
        raise FileNotFoundError(
            f"Cannot find secret file at {secret_path}. Have you run register()?"
        )

    with open(secret_path, "r", encoding="utf-8") as f:
        secret_key = f.read().strip()

    url = f"{server.rstrip('/')}{endpoint}"
    payload = {
        "node_key": node_key,
        "secret_key": secret_key,
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        text = response.text or ""
        # Only treat as success if the server explicitly says "approved"
        if "approved" in text.lower():
            return text
        else:
            raise RuntimeError(f"Node not approved: {text}")
    except requests.RequestException as e:
        return f"Failed to check registration status: {e}"
    except RuntimeError as err:
        return str(err)


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
            output = subprocess.check_output(
                ["wmic", "csproduct", "get", "uuid"],
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL
            )
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
