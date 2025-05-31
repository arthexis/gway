import secrets
import os
from gway import gw
import requests


def register(server: str, node_key: str):
    """
    Registers this node with the given server's registration endpoint.
    
    Generates a secret key, stores it locally, and sends it to the server.

    Args:
        server (str): Base URL of the server (including port).
        node_key (str): Unique identifier for this node.
    """
    if not server or not node_key:
        raise ValueError("Both 'server' and 'node_key' parameters are required.")

    secret_key = secrets.token_urlsafe(32)

    # Save secret key locally
    secret_path = gw.resource("work", f"node.{node_key}.secret")
    os.makedirs(os.path.dirname(secret_path), exist_ok=True)
    with open(secret_path, "w", encoding="utf-8") as f:
        f.write(secret_key)

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
        return f"Failed to register node with server: {e}"
