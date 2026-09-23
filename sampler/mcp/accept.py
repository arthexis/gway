"""Interactive OAuth + MCP acceptance client for a public Gway remote."""

import asyncio
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import secrets
import threading
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen
import webbrowser

from fastmcp import Client
from fastmcp.client.auth import BearerAuth


_CALLBACK = "http://127.0.0.1:8765/callback"


def _json(url):
    with urlopen(url, timeout=10) as response:
        if response.status != 200:
            raise RuntimeError(f"{url} returned {response.status}")
        return json.loads(response.read().decode("utf-8"))


def _form(url, values):
    data = urlencode(values).encode("utf-8")
    request = Request(
        url,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urlopen(request, timeout=10) as response:
        payload = response.read()
        return response.status, json.loads(payload.decode("utf-8") or "{}")


def _pkce(verifier):
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _callback():
    result = {}
    ready = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlsplit(self.path)
            if parsed.path != "/callback":
                self.send_response(404)
                self.end_headers()
                return
            result.update({key: values[-1] for key, values in parse_qs(parsed.query).items()})
            body = b"OAuth callback received. You can return to the terminal."
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            ready.set()

        def log_message(self, format, *args):
            return None

    server = HTTPServer(("127.0.0.1", 8765), Handler)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    return server, thread, ready, result


async def _mcp(resource, bearer, command=None):
    async with Client(resource, auth=BearerAuth(bearer)) as client:
        tools = [tool.name for tool in await client.list_tools()]
        if command is None:
            return tools, None
        result = await client.call_tool("gway", {"command": command})
        return tools, result


def _call(resource, bearer, command=None):
    return asyncio.run(_mcp(resource, bearer, command))


def run(resource):
    """Run the complete public OAuth + MCP acceptance flow."""
    resource = str(resource).rstrip("/")
    parsed = urlsplit(resource)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("acceptance resource must be a public HTTPS URL")

    origin = f"{parsed.scheme}://{parsed.netloc}"
    protected = origin + "/.well-known/oauth-protected-resource" + parsed.path
    auth_meta_url = origin + "/.well-known/oauth-authorization-server"
    client_id = origin + "/.well-known/gway-acceptance-client"

    protected_doc = _json(protected)
    if protected_doc.get("resource") != resource:
        raise RuntimeError("protected-resource metadata does not match resource")
    if protected_doc.get("authorization_servers") != [origin]:
        raise RuntimeError("protected-resource authorization server mismatch")

    auth = _json(auth_meta_url)
    client = _json(client_id)
    if client.get("client_id") != client_id or _CALLBACK not in client.get("redirect_uris", []):
        raise RuntimeError("acceptance client metadata is invalid")

    verifier = secrets.token_urlsafe(48)
    state = secrets.token_urlsafe(24)
    authorize = auth["authorization_endpoint"] + "?" + urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": _CALLBACK,
            "scope": "chatgpt-logs",
            "resource": resource,
            "code_challenge": _pkce(verifier),
            "code_challenge_method": "S256",
            "state": state,
        }
    )

    server, thread, ready, callback = _callback()
    try:
        webbrowser.open(authorize)
        if not ready.wait(300):
            raise RuntimeError(
                "OAuth callback timed out; open the authorization URL in this browser: "
                + authorize
            )
    finally:
        server.server_close()
        thread.join(timeout=1)

    if callback.get("error"):
        raise RuntimeError(f"OAuth authorization failed: {callback['error']}")
    if callback.get("state") != state:
        raise RuntimeError("OAuth callback state mismatch")
    if callback.get("iss") != origin:
        raise RuntimeError("OAuth callback issuer mismatch")
    code = callback.get("code")
    if not code:
        raise RuntimeError("OAuth callback did not contain an authorization code")

    status, issued = _form(
        auth["token_endpoint"],
        {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "resource": resource,
            "code": code,
            "redirect_uri": _CALLBACK,
            "code_verifier": verifier,
        },
    )
    if status != 200 or issued.get("scope") != "chatgpt-logs":
        raise RuntimeError("OAuth token exchange failed or returned wrong scope")

    access = issued["access_token"]
    refresh = issued["refresh_token"]
    tools, _ = _call(resource, access)
    if "gway" not in tools:
        raise RuntimeError("MCP tool discovery did not expose gway")

    commands = {
        "log_sources": "log sources",
        "log_read": "log read arthexis --limit 10",
        "log_tail": "log tail arthexis --limit 1",
        "log_search": "log search timeout arthexis --limit 10",
    }
    for command in commands.values():
        _call(resource, access, command)

    denied = False
    try:
        _, result = _call(resource, access, "clear")
        denied = bool(getattr(result, "is_error", False))
    except Exception:
        denied = True
    if not denied:
        raise RuntimeError("unauthorized clear operation unexpectedly succeeded")

    status, refreshed = _form(
        auth["token_endpoint"],
        {
            "grant_type": "refresh_token",
            "client_id": client_id,
            "resource": resource,
            "refresh_token": refresh,
        },
    )
    if status != 200 or refreshed.get("scope") != "chatgpt-logs":
        raise RuntimeError("OAuth refresh failed or changed scope")
    refreshed_access = refreshed["access_token"]
    _call(resource, refreshed_access, "log sources")

    revoke_data = urlencode({"token": refreshed_access}).encode("utf-8")
    request = Request(
        auth["revocation_endpoint"],
        data=revoke_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urlopen(request, timeout=10) as response:
        if response.status != 200:
            raise RuntimeError("OAuth revocation failed")
        response.read()

    revoked = False
    try:
        _call(resource, refreshed_access, "log sources")
    except Exception:
        revoked = True
    if not revoked:
        raise RuntimeError("revoked OAuth access token still reached MCP")

    return {
        "discovery": "ok",
        "authorization": "ok",
        "token_exchange": "ok",
        "mcp_initialize": "ok",
        "tools": "ok",
        **{name: "ok" for name in commands},
        "unauthorized_clear": "denied",
        "refresh": "ok",
        "revoke": "ok",
        "revoked_access": "denied",
        "o9_acceptance": "ok",
    }
