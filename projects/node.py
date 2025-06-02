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


def manage(*,
    list_all: bool = False,
    node_key: str = None,
    role: str = None,
    revoke: bool = False,
    compact: bool = False,
):
    """
    Manage approved node registrations stored in work/registry.cdv.

    Options:
    --list_all         List all approved (and optionally pending) nodes.
    --node_key=...     Filter by specific node_key.
    --role=...         Filter by role.
    --revoke           Revoke (delete) approval for a given node_key.
    --compact          Return only node_keys (for scripting).
    """
    from gway import gw

    registry_path = ("work", "registry.cdv")
    entries = []

    cdv_file = gw.resource(*registry_path)
    if not cdv_file.exists():
        return "No registry file found."

    with open(cdv_file, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            key, *rest = line.split(':')
            rec = {"node_key": key}
            for part in rest:
                if '=' in part:
                    k, v = part.split('=', 1)
                    rec[k] = v
            entries.append(rec)

    # Filter approved entries only
    approved = [e for e in entries if 'approved' in e]

    if node_key:
        approved = [e for e in approved if e["node_key"] == node_key]
    if role:
        approved = [e for e in approved if e.get("role", "").upper() == role.upper()]

    if revoke:
        if not node_key:
            return "Error: --revoke requires --node_key."
        # Rewrite the cdv file, omitting revoked entry
        remaining = [e for e in entries if e["node_key"] != node_key]
        with open(cdv_file, 'w') as f:
            for rec in remaining:
                parts = [rec["node_key"]] + [f"{k}={v}" for k, v in rec.items() if k != "node_key"]
                f.write(":".join(parts) + "\n")
        return f"Revoked node: {node_key}"

    if compact:
        return [e["node_key"] for e in approved]

    if list_all or node_key or role:
        return approved

    return f"{len(approved)} approved node(s). Use --list_all to view details."


def view_register(**kwargs):
    """
    Register a node using .cdv-based storage with approval handled by gw.approval.

    Accepts:
    - node_key: str
    - secret_key: str
    - start: optional ISO date string, defaults to now
    - end: optional ISO date string
    - credits: optional int
    - role: optional str, defaults to 'ADMIN'
    - message: optional str, included in approval email
    - response: optional 'approve:<key>' or 'deny:<key>'
    """
    import os
    from datetime import datetime
    from gway import gw

    # TODO: Validate that the node_key and secret_key follow a pattern that indicates
    # They were properly calculated by way, and not garbage conjured by the user

    registry_path = ("work", "registry.cdv")
    now_iso = datetime.now().isoformat()

    # 1) If this request has a response parameter, resolve it via gw.approval.resolve()
    response = kwargs.get("response")
    if response:
        status, details = gw.approval.resolve(response)

        if status == "error":
            return f"<p class='error'>{details}</p>"

        # details is the original payload dict we passed to request()
        payload = details
        node_key   = payload.get("node_key")
        secret_key = payload.get("secret_key")
        start      = payload.get("start")
        end        = payload.get("end")
        credits    = payload.get("credits")
        role       = payload.get("role")

        if status == "approved":
            # Store into registry.cdv under node_key
            record = {
                "secret_key": secret_key,
                "start":      start,
            }
            if end:
                record["end"] = end
            if credits:
                record["credits"] = str(credits)
            record["role"] = role

            gw.cdv.store(*registry_path, node_key, **record)
            return f"<p>Node <code>{node_key}</code> approved.</p>"

        elif status == "denied":
            # Mark denied in registry.cdv (optional)
            record = {
                "secret_key": secret_key,
                "denied":     now_iso,
                "start":      start,
            }
            if end:
                record["end"] = end
            if credits:
                record["credits"] = str(credits)
            record["role"] = role

            gw.cdv.store(*registry_path, node_key, **record)
            return f"<p>Node <code>{node_key}</code> denied.</p>"
        
    # TODO: Later we should make the default role level something other than ADMIN

    # 2) If no kwargs provided at all, render the HTML form
    if not kwargs:
        return """
        <h1>Register Node</h1>
        <p>This form is intended for existing customers and local development.</p>
        <form method='post'>
            <label>Node Key: <input name='node_key' required></label><br>
            <label>Secret Key: <input name='secret_key' required></label><br>
            <label>Start (optional): <input name='start' placeholder='YYYY-MM-DD'></label><br>
            <label>End (optional): <input name='end' placeholder='YYYY-MM-DD'></label><br>
            <label>Credits (optional): <input name='credits' type='number'></label><br>
            <label>Role (optional): <input name='role' placeholder='ADMIN'></label><br>
            <label>Message (optional): <br>
                <textarea name='message' rows='4' cols='40' placeholder='Add any message to the admin'></textarea>
            </label><br>
            <button type='submit'>Submit</button>
        </form>
        """

    # 3) Otherwise, process a new registration submission
    node_key   = kwargs.get("node_key")
    secret_key = kwargs.get("secret_key")
    start      = kwargs.get("start") or now_iso
    end        = kwargs.get("end")
    credits    = kwargs.get("credits")
    role       = (kwargs.get("role") or "ADMIN").upper()
    message    = kwargs.get("message", "").strip()

    if not node_key or not secret_key:
        return "<p class='error'>Missing node_key or secret_key.</p>"

    # 3a) Check if this node_key already exists in registry.cdv
    existing = gw.cdv.find(*registry_path, node_key)
    if existing:
        if "start" in existing and "end" in existing and not existing.get("denied"):
            return f"<p>Node <code>{node_key}</code> already registered.</p>"
        if existing.get("denied"):
            return f"<p>Node <code>{node_key}</code> has been denied.</p>"
        return f"<p>Node <code>{node_key}</code> registration is pending approval.</p>"

    # 3b) Build the payload for approval
    payload = {
        "node_key":   node_key,
        "secret_key": secret_key,
        "start":      start,
        "end":        end,
        "credits":    credits,
        "role":       role,
    }
    if message:
        payload["message"] = message

    # 3c) Request approval via gw.approval.request()
    try:
        gw.approval.request(
            category="register",
            data=payload,
            role=role,
            send_email=True
        )
    except Exception as e:
        return f"<p class='error'>Failed to queue approval request: {e}</p>"

    return f"<p>Registration for <code>{node_key}</code> submitted. An admin will review soon.</p>"
