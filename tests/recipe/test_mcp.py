from datetime import datetime, timezone

import pytest

from gway.install.service import ServiceInstallRecord, ServiceInstallState
from gway.logs import LogRecord
from gway.logs import operations as log_operations
from gway.recipe import companion as companion_runtime
from gway.sampler import root as sampler_root
from gway.security.oauth import OAuthRegistry
from gway.security.scopes import ScopeRegistry
from gway.security.tokens import TokenRegistry


pytestmark = pytest.mark.main


MCP_PUBLIC_ORIGIN = "https://remote.example.test"
MCP_RESOURCE = f"{MCP_PUBLIC_ORIGIN}/mcp"


def _issued_token(
    tmp_path,
    monkeypatch,
    *,
    scope="reader",
    operations=("allowed",),
    token="client",
):
    path = tmp_path / "security.sqlite"
    scopes = ScopeRegistry(path)
    tokens = TokenRegistry(path)
    scopes.replace(scope, operations=set(operations))
    issued = tokens.create(token, scopes={scope})
    monkeypatch.setattr(companion_runtime, "TokenRegistry", lambda: tokens)
    return scopes, tokens, issued


def _mcp_companion_recipe(recipe_factory, root, command, *, suffix=""):
    root.mkdir(parents=True, exist_ok=True)
    companion = (sampler_root() / "mcp" / "server.py").read_text(encoding="utf-8")
    companion += suffix
    return recipe_factory(
        name="server",
        root=root,
        body=f"require fastmcp\nserver gway {command!r}\n",
        companion=companion,
    )


def test_mcp_gway_tool_executes_native_pipeline_under_caller_authority(
    gateway, recipe_factory, required_runtime, tmp_path
):
    root = tmp_path / "mcp"
    gateway.produce = gateway.wrap("produce", lambda: "hello")
    gateway.consume = gateway.wrap("consume", lambda value: f"{value}!")
    _mcp_companion_recipe(recipe_factory, root, "produce - consume")
    gateway.ingest(root)

    with gateway.authorized(operations={"mcp.server", "produce", "consume"}):
        assert gateway("mcp server") == "hello!"


def test_mcp_gway_tool_rechecks_each_native_pipeline_operation(
    gateway, recipe_factory, required_runtime, tmp_path
):
    root = tmp_path / "mcp"
    calls = []
    gateway.produce = gateway.wrap("produce", lambda: "hello")

    def consume(value):
        calls.append(value)
        return value

    gateway.consume = gateway.wrap("consume", consume)
    _mcp_companion_recipe(recipe_factory, root, "produce - consume")
    gateway.ingest(root)

    with gateway.authorized(operations={"mcp.server", "produce"}):
        with pytest.raises(RuntimeError, match="Operation is not authorized: consume"):
            gateway("mcp server")

    assert calls == []


def test_mcp_gway_tool_requires_external_authority(
    gateway, recipe_factory, required_runtime, tmp_path
):
    root = tmp_path / "mcp"
    gateway.echo = gateway.wrap("echo_value", lambda value: value)
    recipe = _mcp_companion_recipe(recipe_factory, root, "echo hello")

    with pytest.raises(
        RuntimeError,
        match="External Gateway execution requires an authorization context",
    ):
        gateway(recipe)


def test_mcp_gway_tool_rejects_non_json_result(
    gateway, recipe_factory, required_runtime, tmp_path
):
    root = tmp_path / "mcp"
    gateway.opaque = gateway.wrap("opaque", lambda: {"not-json"})
    _mcp_companion_recipe(recipe_factory, root, "opaque")
    gateway.ingest(root)

    with gateway.authorized(operations={"mcp.server", "opaque"}):
        with pytest.raises(
            RuntimeError,
            match="GWAY result is not MCP-serializable: set",
        ):
            gateway("mcp server")



def test_mcp_stdio_client_lists_and_calls_generic_gway_tool(
    gateway, recipe_factory, required_runtime, tmp_path
):
    root = tmp_path / "mcpstdio"
    gateway.echo = gateway.wrap("echo_value", lambda value: value)
    probe = (
        "\n\ndef probe_stdio(command):\n"
        "    import asyncio\n"
        "    from fastmcp import Client\n"
        "    from fastmcp.client.transports import PythonStdioTransport\n"
        "    async def run():\n"
        "        with _callback_relay() as bridge:\n"
        "            transport = PythonStdioTransport(\n"
        "                str(Path(__file__)),\n"
        "                args=['--parent-bridge', bridge],\n"
        "            )\n"
        "            async with Client(transport) as client:\n"
        "                tools = await client.list_tools()\n"
        "                result = await client.call_tool('gway', {'command': command})\n"
        "                return [tool.name for tool in tools], result.content[0].text\n"
        "    return asyncio.run(run())\n"
    )
    recipe = _mcp_companion_recipe(
        recipe_factory,
        root,
        "echo unused",
        suffix=probe,
    )
    recipe.write_text("require fastmcp\nserver probe stdio 'echo hello'\n", encoding="utf-8")
    gateway.ingest(root)

    with gateway.authorized(operations={"mcpstdio.server", "echo_value"}):
        tools, result = gateway("mcpstdio server")

    assert tools == ["gway", "query"]
    assert result == "hello"


def test_mcp_stdio_authorization_error_does_not_kill_server_session(
    gateway, recipe_factory, required_runtime, tmp_path
):
    root = tmp_path / "mcpstdioerror"
    gateway.allowed = gateway.wrap("allowed", lambda: "ok")
    gateway.denied = gateway.wrap("denied", lambda: "no")
    probe = (
        "\n\ndef probe_stdio():\n"
        "    import asyncio\n"
        "    from fastmcp import Client\n"
        "    from fastmcp.client.transports import PythonStdioTransport\n"
        "    async def run():\n"
        "        with _callback_relay() as bridge:\n"
        "            transport = PythonStdioTransport(\n"
        "                str(Path(__file__)),\n"
        "                args=['--parent-bridge', bridge],\n"
        "            )\n"
        "            async with Client(transport) as client:\n"
        "                first_error = None\n"
        "                try:\n"
        "                    await client.call_tool('gway', {'command': 'denied'})\n"
        "                except Exception as exception:\n"
        "                    first_error = str(exception)\n"
        "                second = await client.call_tool('gway', {'command': 'allowed'})\n"
        "                return first_error, second.content[0].text\n"
        "    return asyncio.run(run())\n"
    )
    recipe = _mcp_companion_recipe(
        recipe_factory,
        root,
        "allowed",
        suffix=probe,
    )
    recipe.write_text("require fastmcp\nserver probe stdio\n", encoding="utf-8")
    gateway.ingest(root)

    with gateway.authorized(operations={"mcpstdioerror.server", "allowed"}):
        error, result = gateway("mcpstdioerror server")

    assert "Operation is not authorized: denied" in error
    assert result == "ok"



def _authenticated_parent_recipe(recipe_factory, root, bearer, command):
    root.mkdir(parents=True, exist_ok=True)
    name = root.name.replace("-", "_")
    return recipe_factory(
        name=name,
        root=root,
        body=f"require placeholder\n{name} probe {bearer!r} {command!r}\n",
        companion=(
            "def probe(bearer, command):\n"
            "    return _gway_parent.execute_authenticated(bearer, command)\n"
        ),
    )


def test_parent_authenticated_execution_uses_token_scope(
    gateway, recipe_factory, required_runtime, tmp_path, monkeypatch
):
    _, _, issued = _issued_token(tmp_path, monkeypatch)

    gateway.allowed = gateway.wrap("allowed", lambda: "ok")
    recipe = _authenticated_parent_recipe(
        recipe_factory,
        tmp_path / "auth",
        issued.bearer,
        "allowed",
    )

    assert gateway(recipe) == "ok"
    assert gateway.authorization is None


def test_parent_authenticated_execution_denies_operation_outside_token_scope(
    gateway, recipe_factory, required_runtime, tmp_path, monkeypatch
):
    path = tmp_path / "security.sqlite"
    scopes = ScopeRegistry(path)
    tokens = TokenRegistry(path)
    scopes.replace("reader", operations={"allowed"})
    issued = tokens.create("client", scopes={"reader"})
    monkeypatch.setattr(companion_runtime, "TokenRegistry", lambda: tokens)

    gateway.denied = gateway.wrap("denied", lambda: "no")
    recipe = _authenticated_parent_recipe(
        recipe_factory,
        tmp_path / "auth-denied",
        issued.bearer,
        "denied",
    )

    with pytest.raises(RuntimeError, match="Operation is not authorized: denied"):
        gateway(recipe)

    assert gateway.authorization is None


def test_parent_authenticated_execution_rejects_invalid_bearer_uniformly(
    gateway, recipe_factory, required_runtime, tmp_path, monkeypatch
):
    tokens = TokenRegistry(tmp_path / "security.sqlite")
    monkeypatch.setattr(companion_runtime, "TokenRegistry", lambda: tokens)

    recipe = _authenticated_parent_recipe(
        recipe_factory,
        tmp_path / "auth-invalid",
        "gwt_missing_wrong",
        "clear",
    )

    with pytest.raises(RuntimeError, match="Invalid bearer token"):
        gateway(recipe)

    assert gateway.authorization is None


def test_parent_authenticated_execution_rejects_disabled_token(
    gateway, recipe_factory, required_runtime, tmp_path, monkeypatch
):
    _, tokens, issued = _issued_token(tmp_path, monkeypatch)
    tokens.disable("client")

    gateway.allowed = gateway.wrap("allowed", lambda: "ok")
    recipe = _authenticated_parent_recipe(
        recipe_factory,
        tmp_path / "auth-disabled",
        issued.bearer,
        "allowed",
    )

    with pytest.raises(RuntimeError, match="Invalid bearer token"):
        gateway(recipe)

    assert gateway.authorization is None



def _mcp_http_probe_suffix():
    return r'''
def probe_http(bearer, command, second_bearer=None, second_command=None, tool="gway"):
    import asyncio
    import os
    import socket
    import subprocess
    import sys
    import time

    from fastmcp import Client
    from fastmcp.client.auth import BearerAuth

    def free_port():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            return listener.getsockname()[1]

    def wait_ready(port, process):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"MCP HTTP server exited with {process.returncode}")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                    return
            except OSError:
                time.sleep(0.05)
        raise RuntimeError("MCP HTTP server did not become ready")

    async def call(url, credential, value):
        auth = None if credential == "__missing__" else BearerAuth(credential)
        try:
            async with Client(url, auth=auth) as client:
                tools = await client.list_tools()
                try:
                    result = await client.call_tool(tool, {"command": value})
                except Exception as exception:
                    return [tool.name for tool in tools], None, str(exception)
                return [tool.name for tool in tools], result.content[0].text, None
        except Exception as exception:
            return [], None, str(exception)

    async def run(url):
        first = await call(url, bearer, command)
        if second_command is None:
            return first
        first_task = asyncio.create_task(call(url, bearer, command))
        second_task = asyncio.create_task(
            call(url, second_bearer, second_command)
        )
        return await asyncio.gather(first_task, second_task)

    port = free_port()
    with _callback_relay() as bridge:
        process = subprocess.Popen(
            [
                sys.executable,
                str(Path(__file__)),
                "--parent-bridge",
                bridge,
                "--transport",
                "http",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--path",
                "/mcp",
                "--public-origin",
                "https://remote.example.test",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            wait_ready(port, process)
            return asyncio.run(run(f"http://127.0.0.1:{port}/mcp"))
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def probe_challenge(credential="__missing__"):
    import http.client
    import json
    import os
    import socket
    import subprocess
    import sys
    import time

    def free_port():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            return listener.getsockname()[1]

    def wait_ready(port, process):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"MCP HTTP server exited with {process.returncode}")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                    return
            except OSError:
                time.sleep(0.05)
        raise RuntimeError("MCP HTTP server did not become ready")

    port = free_port()
    with _callback_relay() as bridge:
        process = subprocess.Popen(
            [
                sys.executable,
                str(Path(__file__)),
                "--parent-bridge",
                bridge,
                "--transport",
                "http",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--path",
                "/mcp",
                "--public-origin",
                "https://remote.example.test",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            wait_ready(port, process)
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            }
            if credential != "__missing__":
                headers["Authorization"] = f"Bearer {credential}"
            body = json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {},
                        "clientInfo": {"name": "test", "version": "1"},
                    },
                }
            )
            connection.request("POST", "/mcp", body=body, headers=headers)
            response = connection.getresponse()
            status = response.status
            challenge = response.getheader("WWW-Authenticate")
            response.read()
            connection.close()
            return status, challenge
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
'''


def _mcp_http_recipe(recipe_factory, root):
    root.mkdir(parents=True, exist_ok=True)
    recipe = _mcp_companion_recipe(
        recipe_factory,
        root,
        "clear",
        suffix=_mcp_http_probe_suffix(),
    )
    return recipe


def test_mcp_http_real_client_uses_bearer_scope(
    gateway, recipe_factory, required_runtime, tmp_path, monkeypatch
):
    _, _, issued = _issued_token(
        tmp_path,
        monkeypatch,
        token="http-client",
    )

    gateway.allowed = gateway.wrap("allowed", lambda: "ok")
    recipe = _mcp_http_recipe(recipe_factory, tmp_path / "mcphttp")
    recipe.write_text(
        f"require fastmcp\nserver probe http {issued.bearer!r} allowed\n",
        encoding="utf-8",
    )
    gateway.ingest(recipe.parent)

    with gateway.authorized(operations={"mcphttp.server"}):
        tools, result, error = gateway("mcphttp server")

    assert tools == ["gway", "query"]
    assert result == "ok"
    assert error is None







def test_mcp_http_query_uses_bearer_scope_and_forces_no_mutation(
    gateway, recipe_factory, required_runtime, tmp_path, monkeypatch
):
    _, _, issued = _issued_token(
        tmp_path,
        monkeypatch,
        operations=("observe", "restart"),
        token="http-query-client",
    )
    seen = []

    def observe(*, mutate=False):
        seen.append(("observe", mutate))
        return "observed"

    def restart():
        seen.append(("restart", True))
        return "restarted"

    gateway.observe = gateway.wrap("observe", observe)
    gateway.restart = gateway.wrap("restart", restart)
    recipe = _mcp_http_recipe(recipe_factory, tmp_path / "mcphttpquery")
    recipe.write_text(
        "require fastmcp\n"
        f"server probe http {issued.bearer!r} observe --tool query\n",
        encoding="utf-8",
    )
    gateway.ingest(recipe.parent)

    with gateway.authorized(operations={"mcphttpquery.server"}):
        tools, result, error = gateway("mcphttpquery server")

    assert tools == ["gway", "query"]
    assert result == "observed"
    assert error is None
    assert seen == [("observe", False)]

    recipe.write_text(
        "require fastmcp\n"
        f"server probe http {issued.bearer!r} restart --tool query\n",
        encoding="utf-8",
    )

    with gateway.authorized(operations={"mcphttpquery.server"}):
        tools, result, error = gateway("mcphttpquery server")

    assert tools == ["gway", "query"]
    assert result is None
    assert "does not support non-mutating execution" in error
    assert seen == [("observe", False)]

def _issued_oauth_token(tmp_path, monkeypatch, *, resource=MCP_RESOURCE):
    path = tmp_path / "security.sqlite"
    scopes = ScopeRegistry(path)
    tokens = TokenRegistry(path)
    oauth = OAuthRegistry(path)
    scopes.replace("reader", operations={"allowed"})
    tokens.create("operator", scopes={"reader"})
    oauth.link("chatgpt", "operator")
    grant = oauth.create_grant(
        "chatgpt",
        "chatgpt-client",
        scopes={"reader"},
        resource=resource,
    )
    issued = oauth.issue_tokens(grant.id)
    monkeypatch.setattr(companion_runtime, "OAuthRegistry", lambda: oauth)
    return scopes, tokens, oauth, issued


def test_mcp_http_real_client_accepts_oauth_access_token(
    gateway, recipe_factory, required_runtime, tmp_path, monkeypatch
):
    _, _, _, issued = _issued_oauth_token(tmp_path, monkeypatch)

    gateway.allowed = gateway.wrap("allowed", lambda: "ok")
    recipe = _mcp_http_recipe(recipe_factory, tmp_path / "mcpoauth")
    recipe.write_text(
        f"require fastmcp\nserver probe http {issued.access_token!r} allowed\n",
        encoding="utf-8",
    )
    gateway.ingest(recipe.parent)

    with gateway.authorized(operations={"mcpoauth.server"}):
        tools, result, error = gateway("mcpoauth server")

    assert tools == ["gway", "query"]
    assert result == "ok"
    assert error is None


def test_mcp_http_oauth_token_uses_live_named_scope_after_issuance(
    gateway, recipe_factory, required_runtime, tmp_path, monkeypatch
):
    scopes, _, _, issued = _issued_oauth_token(tmp_path, monkeypatch)
    scopes.replace("reader", operations={"new_allowed"})

    gateway.allowed = gateway.wrap("allowed", lambda: "old")
    gateway.new_allowed = gateway.wrap("new_allowed", lambda: "new")
    recipe = _mcp_http_recipe(recipe_factory, tmp_path / "mcpoauthlive")
    recipe.write_text(
        "require fastmcp\n"
        f"server probe http {issued.access_token!r} allowed "
        f"{issued.access_token!r} new_allowed\n",
        encoding="utf-8",
    )
    gateway.ingest(recipe.parent)

    with gateway.authorized(operations={"mcpoauthlive.server"}):
        results = gateway("mcpoauthlive server")

    first, second = results
    assert first[0] == ["gway", "query"]
    assert first[1] is None
    assert "Operation is not authorized: allowed" in first[2]
    assert second == (["gway", "query"], "new", None)


def test_mcp_http_oauth_authority_does_not_inherit_trusted_recipe_capability(
    gateway, recipe_factory, required_runtime, tmp_path, monkeypatch
):
    _, _, _, issued = _issued_oauth_token(tmp_path, monkeypatch)

    recipe = _mcp_http_recipe(recipe_factory, tmp_path / "mcpoauthcapability")
    recipe.write_text(
        f"require fastmcp\nserver probe http {issued.access_token!r} clear\n",
        encoding="utf-8",
    )
    gateway.ingest(recipe.parent)

    with gateway.authorized(operations={"mcpoauthcapability.server"}):
        tools, result, error = gateway("mcpoauthcapability server")

    assert tools == ["gway", "query"]
    assert result is None
    assert "Operation is not authorized: clear" in error
    assert "401" not in error


def test_mcp_http_rejects_oauth_token_for_different_resource(
    gateway, recipe_factory, required_runtime, tmp_path, monkeypatch
):
    _, _, _, issued = _issued_oauth_token(
        tmp_path,
        monkeypatch,
        resource="https://remote.example.test/api",
    )

    recipe = _mcp_http_recipe(recipe_factory, tmp_path / "mcpoauthwrongresource")
    recipe.write_text(
        f"require fastmcp\nserver probe http {issued.access_token!r} clear\n",
        encoding="utf-8",
    )
    gateway.ingest(recipe.parent)

    with gateway.authorized(operations={"mcpoauthwrongresource.server"}):
        tools, result, error = gateway("mcpoauthwrongresource server")

    assert tools == []
    assert result is None
    assert error is not None
    assert "Server returned an error response" in error


def test_mcp_http_rejects_revoked_oauth_access_token(
    gateway, recipe_factory, required_runtime, tmp_path, monkeypatch
):
    _, _, oauth, issued = _issued_oauth_token(tmp_path, monkeypatch)
    oauth.revoke(issued.access_token)

    recipe = _mcp_http_recipe(recipe_factory, tmp_path / "mcpoauthrevoked")
    recipe.write_text(
        f"require fastmcp\nserver probe http {issued.access_token!r} clear\n",
        encoding="utf-8",
    )
    gateway.ingest(recipe.parent)

    with gateway.authorized(operations={"mcpoauthrevoked.server"}):
        tools, result, error = gateway("mcpoauthrevoked server")

    assert tools == []
    assert result is None
    assert error is not None
    assert "Server returned an error response" in error


@pytest.mark.parametrize(
    ("credential", "root_name"),
    [
        ("__missing__", "mcpchallengemissing"),
        ("gwt_missing_wrong", "mcpchallengeinvalid"),
    ],
)
def test_mcp_http_authentication_challenge_points_to_protected_resource_metadata(
    gateway,
    recipe_factory,
    required_runtime,
    tmp_path,
    monkeypatch,
    credential,
    root_name,
):
    tokens = TokenRegistry(tmp_path / "security.sqlite")
    monkeypatch.setattr(companion_runtime, "TokenRegistry", lambda: tokens)

    recipe = _mcp_http_recipe(recipe_factory, tmp_path / root_name)
    recipe.write_text(
        f"require fastmcp\nserver probe_challenge {credential!r}\n",
        encoding="utf-8",
    )
    gateway.ingest(recipe.parent)

    operation = f"{root_name}.server"
    with gateway.authorized(operations={operation}):
        status, challenge = gateway(f"{root_name} server")

    assert status == 401
    assert challenge.startswith("Bearer")
    assert (
        'resource_metadata="'
        "https://remote.example.test/.well-known/oauth-protected-resource/mcp"
        '"' in challenge
    )


def test_mcp_http_scope_denial_is_tool_error_not_authentication_failure(
    gateway, recipe_factory, required_runtime, tmp_path, monkeypatch
):
    path = tmp_path / "security.sqlite"
    scopes = ScopeRegistry(path)
    tokens = TokenRegistry(path)
    scopes.replace("reader", operations={"allowed"})
    issued = tokens.create("http-client", scopes={"reader"})
    monkeypatch.setattr(companion_runtime, "TokenRegistry", lambda: tokens)

    gateway.denied = gateway.wrap("denied", lambda: "no")
    recipe = _mcp_http_recipe(recipe_factory, tmp_path / "mcphttpdenied")
    recipe.write_text(
        f"require fastmcp\nserver probe http {issued.bearer!r} denied\n",
        encoding="utf-8",
    )
    gateway.ingest(recipe.parent)

    with gateway.authorized(operations={"mcphttpdenied.server"}):
        tools, result, error = gateway("mcphttpdenied server")

    assert tools == ["gway", "query"]
    assert result is None
    assert "Operation is not authorized: denied" in error
    assert "Invalid bearer token" not in error


@pytest.mark.parametrize("credential", ["__missing__", "gwt_missing_wrong"])
def test_mcp_http_rejects_missing_and_invalid_bearer(
    gateway,
    recipe_factory,
    required_runtime,
    tmp_path,
    monkeypatch,
    credential,
):
    tokens = TokenRegistry(tmp_path / "security.sqlite")
    monkeypatch.setattr(companion_runtime, "TokenRegistry", lambda: tokens)

    recipe = _mcp_http_recipe(
        recipe_factory,
        tmp_path / (
            "mcphttpmissing" if credential == "__missing__" else "mcphttpinvalid"
        ),
    )
    value = repr(credential)
    recipe.write_text(
        f"require fastmcp\nserver probe http {value} clear\n",
        encoding="utf-8",
    )
    gateway.ingest(recipe.parent)

    operation = recipe.parent.name.replace("-", "_") + ".server"
    with gateway.authorized(operations={operation}):
        tools, result, error = gateway(operation.replace(".", " "))

    assert tools == []
    assert result is None
    assert error is not None
    assert "Server returned an error response" in error


def test_mcp_http_rejects_disabled_bearer(
    gateway, recipe_factory, required_runtime, tmp_path, monkeypatch
):
    _, tokens, issued = _issued_token(
        tmp_path,
        monkeypatch,
        token="http-client",
    )
    tokens.disable("http-client")

    gateway.allowed = gateway.wrap("allowed", lambda: "ok")
    recipe = _mcp_http_recipe(recipe_factory, tmp_path / "mcphttpdisabled")
    recipe.write_text(
        f"require fastmcp\nserver probe http {issued.bearer!r} allowed\n",
        encoding="utf-8",
    )
    gateway.ingest(recipe.parent)

    with gateway.authorized(operations={"mcphttpdisabled.server"}):
        tools, result, error = gateway("mcphttpdisabled server")

    assert tools == []
    assert result is None
    assert error is not None
    assert "Server returned an error response" in error


def test_mcp_http_concurrent_clients_keep_distinct_scopes(
    gateway, recipe_factory, required_runtime, tmp_path, monkeypatch
):
    path = tmp_path / "security.sqlite"
    scopes = ScopeRegistry(path)
    tokens = TokenRegistry(path)
    scopes.replace("alpha-scope", operations={"alpha"})
    scopes.replace("beta-scope", operations={"beta"})
    alpha_token = tokens.create("alpha-client", scopes={"alpha-scope"})
    beta_token = tokens.create("beta-client", scopes={"beta-scope"})
    monkeypatch.setattr(companion_runtime, "TokenRegistry", lambda: tokens)

    gateway.alpha = gateway.wrap("alpha", lambda: "alpha-ok")
    gateway.beta = gateway.wrap("beta", lambda: "beta-ok")
    recipe = _mcp_http_recipe(recipe_factory, tmp_path / "mcphttpconcurrent")
    recipe.write_text(
        "require fastmcp\n"
        f"server probe http {alpha_token.bearer!r} alpha "
        f"{beta_token.bearer!r} beta\n",
        encoding="utf-8",
    )
    gateway.ingest(recipe.parent)

    with gateway.authorized(operations={"mcphttpconcurrent.server"}):
        results = gateway("mcphttpconcurrent server")

    assert results == [
        (["gway", "query"], "alpha-ok", None),
        (["gway", "query"], "beta-ok", None),
    ]



def _mcp_log_http_probe_suffix():
    return r'''
def probe_log_http(bearer, tool="gway", extra_command="clear"):
    import asyncio
    import json
    import os
    import socket
    import subprocess
    import sys
    import time

    from fastmcp import Client
    from fastmcp.client.auth import BearerAuth

    def free_port():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            return listener.getsockname()[1]

    def wait_ready(port, process):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"MCP HTTP server exited with {process.returncode}")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                    return
            except OSError:
                time.sleep(0.05)
        raise RuntimeError("MCP HTTP server did not become ready")

    async def run(url):
        async with Client(url, auth=BearerAuth(bearer)) as client:
            tools = [tool.name for tool in await client.list_tools()]
            commands = [
                "log sources",
                "log read arthexis --limit 10",
                "log tail arthexis --limit 1",
                "log search timeout arthexis --limit 10",
                extra_command,
            ]
            results = []
            for command in commands:
                try:
                    result = await client.call_tool(tool, {"command": command})
                except Exception as exception:
                    results.append({"error": str(exception)})
                else:
                    results.append({"value": json.loads(result.content[0].text)})
            return tools, results

    port = free_port()
    with _callback_relay() as bridge:
        process = subprocess.Popen(
            [
                sys.executable,
                str(Path(__file__)),
                "--parent-bridge",
                bridge,
                "--transport",
                "http",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--path",
                "/mcp",
                "--public-origin",
                "https://remote.example.test",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            wait_ready(port, process)
            return asyncio.run(run(f"http://127.0.0.1:{port}/mcp"))
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
'''



def _issued_chatgpt_logs_oauth(tmp_path, monkeypatch, *, extra_operations=()):
    security_path = tmp_path / "security.sqlite"
    scopes = ScopeRegistry(security_path)
    tokens = TokenRegistry(security_path)
    oauth = OAuthRegistry(security_path)
    operations = {
        "log.sources",
        "log.read",
        "log.tail",
        "log.search",
        *extra_operations,
    }
    scopes.replace(
        "chatgpt-logs",
        operations=operations,
        environment=(),
    )
    tokens.create("chatgpt-operator", scopes={"chatgpt-logs"})
    oauth.link("chatgpt", "chatgpt-operator")
    grant = oauth.create_grant(
        "chatgpt",
        "chatgpt-client",
        scopes={"chatgpt-logs"},
        resource=MCP_RESOURCE,
    )
    issued = oauth.issue_tokens(grant.id)
    monkeypatch.setattr(companion_runtime, "OAuthRegistry", lambda: oauth)
    return scopes, tokens, oauth, issued


def _install_log_acceptance_fixture(tmp_path, monkeypatch):
    state = ServiceInstallState(tmp_path / "services-installed")
    state.put(
        "arthexis",
        [
            ServiceInstallRecord(
                project="arthexis",
                service="web",
                backend_id="arthexis-web.service",
                backend="systemd",
                system=False,
            ),
        ],
    )
    monkeypatch.setattr(log_operations, "_install_state", lambda: state)
    monkeypatch.setattr(log_operations, "_journal_available", lambda: True)

    records = [
        LogRecord(
            timestamp=datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc),
            source="arthexis/web",
            message="startup complete",
            level="INFO",
            pid=101,
            unit="arthexis-web.service",
            metadata={},
        ),
        LogRecord(
            timestamp=datetime(2026, 9, 22, 12, 1, tzinfo=timezone.utc),
            source="arthexis/web",
            message="timeout waiting for charger",
            level="ERROR",
            pid=101,
            unit="arthexis-web.service",
            metadata={},
        ),
    ]

    def fake_read_journal(sources, *, grep=None, reverse=False, limit=None, **kwargs):
        selected = list(records)
        if grep is not None:
            selected = [record for record in selected if "timeout" in record.message]
        selected.sort(key=lambda record: record.timestamp, reverse=reverse)
        if limit is not None:
            selected = selected[: int(limit)]
        return selected

    monkeypatch.setattr(log_operations, "read_journal", fake_read_journal)


def _assert_chatgpt_log_results(tools, results):
    assert tools == ["gway", "query"]
    for index, command in enumerate(("sources", "read", "tail", "search")):
        assert "value" in results[index], (command, results[index])

    assert [item["identity"] for item in results[0]["value"]] == [
        "gway",
        "arthexis",
        "arthexis/web",
    ]
    assert [item["message"] for item in results[1]["value"]] == [
        "startup complete",
        "timeout waiting for charger",
    ]
    assert [item["message"] for item in results[2]["value"]] == [
        "timeout waiting for charger",
    ]
    assert [item["message"] for item in results[3]["value"]] == [
        "timeout waiting for charger",
    ]


def test_chatgpt_logs_oauth_query_acceptance_and_refresh(
    gateway, recipe_factory, required_runtime, tmp_path, monkeypatch
):
    scopes, _, oauth, issued = _issued_chatgpt_logs_oauth(tmp_path, monkeypatch)
    _install_log_acceptance_fixture(tmp_path, monkeypatch)

    root = tmp_path / "mcpchatgptlogs"
    recipe = _mcp_companion_recipe(
        recipe_factory,
        root,
        "clear",
        suffix=_mcp_log_http_probe_suffix(),
    )
    recipe.write_text(
        "require fastmcp\n"
        f"server probe_log_http {issued.access_token!r} --tool query "
        "--extra-command 'service status arthexis'\n",
        encoding="utf-8",
    )
    gateway.ingest(root)

    with gateway.authorized(operations={"mcpchatgptlogs.server"}):
        tools, results = gateway("mcpchatgptlogs server")

    _assert_chatgpt_log_results(tools, results)
    assert "Operation is not authorized: service.status" in results[4]["error"]

    refreshed = oauth.rotate_refresh(
        issued.refresh_token,
        client_id="chatgpt-client",
        resource=MCP_RESOURCE,
    )
    scopes.replace(
        "chatgpt-logs",
        operations={"log.sources", "log.read", "log.tail", "log.search"},
        environment=(),
    )
    recipe.write_text(
        "require fastmcp\n"
        f"server probe_log_http {refreshed.access_token!r} --tool query\n",
        encoding="utf-8",
    )

    with gateway.authorized(operations={"mcpchatgptlogs.server"}):
        refreshed_tools, refreshed_results = gateway("mcpchatgptlogs server")

    _assert_chatgpt_log_results(refreshed_tools, refreshed_results)
    assert "Operation is not authorized: clear" in refreshed_results[4]["error"]
    assert "GWAY_SECRET" not in repr((results, refreshed_results))


def test_chatgpt_query_mutation_ceiling_survives_broader_oauth_scope(
    gateway, recipe_factory, required_runtime, tmp_path, monkeypatch
):
    _, _, oauth, issued = _issued_chatgpt_logs_oauth(
        tmp_path,
        monkeypatch,
        extra_operations={"restart"},
    )
    called = []

    def restart():
        called.append(True)
        return "restarted"

    gateway.restart = gateway.wrap("restart", restart)
    root = tmp_path / "mcpchatgptmutation"
    recipe = _mcp_http_recipe(recipe_factory, root)
    recipe.write_text(
        "require fastmcp\n"
        f"server probe http {issued.access_token!r} restart --tool query\n",
        encoding="utf-8",
    )
    gateway.ingest(root)

    with gateway.authorized(operations={"mcpchatgptmutation.server"}):
        tools, result, error = gateway("mcpchatgptmutation server")

    assert tools == ["gway", "query"]
    assert result is None
    assert "does not support non-mutating execution" in error
    assert called == []


def test_mcp_http_logs_read_scope_uses_canonical_gway_operations(
    gateway, recipe_factory, required_runtime, tmp_path, monkeypatch
):
    security_path = tmp_path / "security.sqlite"
    scopes = ScopeRegistry(security_path)
    tokens = TokenRegistry(security_path)
    scopes.replace(
        "logs-read",
        operations={"log.sources", "log.read", "log.tail", "log.search"},
        environment=(),
    )
    issued = tokens.create("logs-client", scopes={"logs-read"})
    monkeypatch.setattr(companion_runtime, "TokenRegistry", lambda: tokens)

    state = ServiceInstallState(tmp_path / "services-installed")
    state.put(
        "arthexis",
        [
            ServiceInstallRecord(
                project="arthexis",
                service="web",
                backend_id="arthexis-web.service",
                backend="systemd",
                system=False,
            ),
        ],
    )
    monkeypatch.setattr(log_operations, "_install_state", lambda: state)
    monkeypatch.setattr(log_operations, "_journal_available", lambda: True)

    records = [
        LogRecord(
            timestamp=datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc),
            source="arthexis/web",
            message="startup complete",
            level="INFO",
            pid=101,
            unit="arthexis-web.service",
            metadata={},
        ),
        LogRecord(
            timestamp=datetime(2026, 9, 22, 12, 1, tzinfo=timezone.utc),
            source="arthexis/web",
            message="timeout waiting for charger",
            level="ERROR",
            pid=101,
            unit="arthexis-web.service",
            metadata={},
        ),
    ]

    def fake_read_journal(sources, *, grep=None, reverse=False, limit=None, **kwargs):
        selected = list(records)
        if grep is not None:
            selected = [record for record in selected if "timeout" in record.message]
        selected.sort(key=lambda record: record.timestamp, reverse=reverse)
        if limit is not None:
            selected = selected[: int(limit)]
        return selected

    monkeypatch.setattr(log_operations, "read_journal", fake_read_journal)

    root = tmp_path / "mcplogs"
    recipe = _mcp_companion_recipe(
        recipe_factory,
        root,
        "clear",
        suffix=_mcp_log_http_probe_suffix(),
    )
    recipe.write_text(
        f"require fastmcp\nserver probe_log_http {issued.bearer!r}\n",
        encoding="utf-8",
    )
    gateway.ingest(root)

    with gateway.authorized(operations={"mcplogs.server"}):
        tools, results = gateway("mcplogs server")

    assert tools == ["gway", "query"]

    for index, command in enumerate(("sources", "read", "tail", "search")):
        assert "value" in results[index], (command, results[index])

    source_result = results[0]["value"]
    assert [item["identity"] for item in source_result] == [
        "gway",
        "arthexis",
        "arthexis/web",
    ]

    read_result = results[1]["value"]
    assert [item["message"] for item in read_result] == [
        "startup complete",
        "timeout waiting for charger",
    ]

    tail_result = results[2]["value"]
    assert [item["message"] for item in tail_result] == [
        "timeout waiting for charger",
    ]

    search_result = results[3]["value"]
    assert [item["message"] for item in search_result] == [
        "timeout waiting for charger",
    ]

    assert "Operation is not authorized: clear" in results[4]["error"]
    assert "GWAY_SECRET" not in repr(results)



def _maintained_companion_with_http_stub():
    companion = (sampler_root() / "mcp" / "server.py").read_text(
        encoding="utf-8"
    )
    return companion + (
        "\n\ndef run_http(*, host='127.0.0.1', port=8000, path='/mcp', endpoint=None, public_origin=None):\n"
        "    return {'host': host, 'port': int(port), 'path': path}\n"
    )


def test_maintained_mcp_recipe_serves_http_with_safe_defaults(
    gateway, recipe_factory, required_runtime, tmp_path
):
    root = tmp_path / "mcpmaintained"
    root.mkdir()
    maintained_rx = (sampler_root() / "mcp" / "server.rx").read_text(
        encoding="utf-8"
    )
    maintained_py = _maintained_companion_with_http_stub()
    recipe = recipe_factory(
        name="server",
        root=root,
        body=maintained_rx,
        companion=maintained_py,
    )

    result = gateway(recipe)

    assert result == {
        "host": "127.0.0.1",
        "port": 8000,
        "path": "/mcp",
    }


def test_maintained_mcp_recipe_exposes_deployment_parameters():
    recipe = (sampler_root() / "mcp" / "server.rx").read_text(encoding="utf-8")

    assert "[host|127.0.0.1]" in recipe
    assert "[port|8000]" in recipe
    assert "[route|/mcp]" in recipe
    assert "--endpoint [endpoint|http://127.0.0.1:8000/mcp]" in recipe
    assert "mcp_host" not in recipe
    assert "mcp_port" not in recipe
    assert "mcp_public_origin" not in recipe


def test_mcp_endpoint_derives_public_origin_and_requires_matching_path(
    gateway, recipe_factory, required_runtime, tmp_path
):
    root = tmp_path / "mcpendpoint"
    root.mkdir()
    maintained_py = (sampler_root() / "mcp" / "server.py").read_text(
        encoding="utf-8"
    )
    maintained_py += (
        "\n\ndef run_http_probe(*, host='127.0.0.1', port=8000, path='/mcp', "
        "endpoint=None):\n"
        "    return _endpoint_origin(endpoint, path)\n"
    )
    recipe = recipe_factory(
        name="server",
        root=root,
        body=(
            "require fastmcp\n"
            "server run_http_probe --path /mcp "
            "--endpoint https://remote.example.test/mcp\n"
        ),
        companion=maintained_py,
    )

    assert gateway(recipe) == "https://remote.example.test"


def test_mcp_endpoint_rejects_path_mismatch(
    gateway, recipe_factory, required_runtime, tmp_path
):
    root = tmp_path / "mcpendpointmismatch"
    root.mkdir()
    maintained_py = (sampler_root() / "mcp" / "server.py").read_text(
        encoding="utf-8"
    )
    maintained_py += (
        "\n\ndef run_http_probe(endpoint, path='/mcp'):\n"
        "    return _endpoint_origin(endpoint, path)\n"
    )
    recipe = recipe_factory(
        name="server",
        root=root,
        body=(
            "require fastmcp\n"
            "server run_http_probe https://remote.example.test/other "
            "--path /mcp\n"
        ),
        companion=maintained_py,
    )

    with pytest.raises(RuntimeError, match="does not match local path"):
        gateway(recipe)


def test_mcp_serve_allows_explicit_http_bind_configuration(
    gateway, recipe_factory, required_runtime, tmp_path
):
    root = tmp_path / "mcpconfigured"
    root.mkdir()
    maintained_py = (sampler_root() / "mcp" / "server.py").read_text(
        encoding="utf-8"
    )
    maintained_py += (
        "\n\ndef run_http(*, host='127.0.0.1', port=8000, path='/mcp', endpoint=None, public_origin=None):\n"
        "    return {'host': host, 'port': int(port), 'path': path}\n"
    )
    recipe = recipe_factory(
        name="server",
        root=root,
        body=(
            "require fastmcp\n"
            "server serve 127.0.0.2 8123 /custom-mcp\n"
        ),
        companion=maintained_py,
    )

    result = gateway(recipe)

    assert result == {
        "host": "127.0.0.2",
        "port": 8123,
        "path": "/custom-mcp",
    }



def test_mcp_stdio_query_is_listed_read_only_and_enforces_no_mutation(
    gateway, recipe_factory, required_runtime, tmp_path
):
    root = tmp_path / "mcpstdioquery"
    seen = []

    def observe(*, mutate=False):
        seen.append(("observe", mutate))
        return "observed"

    def restart():
        seen.append(("restart", True))
        return "restarted"

    gateway.observe = gateway.wrap("observe", observe)
    gateway.restart = gateway.wrap("restart", restart)

    probe = (
        "\n\ndef probe_query():\n"
        "    import asyncio\n"
        "    from fastmcp import Client\n"
        "    from fastmcp.client.transports import PythonStdioTransport\n"
        "    async def run():\n"
        "        with _callback_relay() as bridge:\n"
        "            transport = PythonStdioTransport(\n"
        "                str(Path(__file__)),\n"
        "                args=['--parent-bridge', bridge],\n"
        "            )\n"
        "            async with Client(transport) as client:\n"
        "                tools = await client.list_tools()\n"
        "                query_tool = next(tool for tool in tools if tool.name == 'query')\n"
        "                safe = await client.call_tool('query', {'command': 'observe'})\n"
        "                error = None\n"
        "                try:\n"
        "                    await client.call_tool('query', {'command': 'restart'})\n"
        "                except Exception as exception:\n"
        "                    error = str(exception)\n"
        "                annotation = getattr(query_tool, 'annotations', None)\n"
        "                read_only = getattr(annotation, 'readOnlyHint', None)\n"
        "                if read_only is None and isinstance(annotation, dict):\n"
        "                    read_only = annotation.get('readOnlyHint')\n"
        "                return [tool.name for tool in tools], read_only, safe.content[0].text, error\n"
        "    return asyncio.run(run())\n"
    )
    recipe = _mcp_companion_recipe(
        recipe_factory,
        root,
        "observe",
        suffix=probe,
    )
    recipe.write_text("require fastmcp\nserver probe query\n", encoding="utf-8")
    gateway.ingest(root)

    with gateway.authorized(
        operations={"mcpstdioquery.server", "observe", "restart"}
    ):
        tools, read_only, result, error = gateway("mcpstdioquery server")

    assert tools == ["gway", "query"]
    assert read_only is True
    assert result == "observed"
    assert "does not support non-mutating execution" in error
    assert seen == [("observe", False)]


def test_mcp_query_does_not_change_generic_gway_mutation_behavior(
    gateway, recipe_factory, required_runtime, tmp_path
):
    root = tmp_path / "mcpgwaymutating"
    seen = []

    def mutate_now():
        seen.append("mutated")
        return "done"

    gateway.mutate_now = gateway.wrap("mutate_now", mutate_now)
    probe = (
        "\n\ndef probe_gway_mutation():\n"
        "    import asyncio\n"
        "    from fastmcp import Client\n"
        "    from fastmcp.client.transports import PythonStdioTransport\n"
        "    async def run():\n"
        "        with _callback_relay() as bridge:\n"
        "            transport = PythonStdioTransport(str(Path(__file__)), args=['--parent-bridge', bridge])\n"
        "            async with Client(transport) as client:\n"
        "                result = await client.call_tool('gway', {'command': 'mutate_now'})\n"
        "                return result.content[0].text\n"
        "    return asyncio.run(run())\n"
    )
    recipe = _mcp_companion_recipe(
        recipe_factory,
        root,
        "mutate_now",
        suffix=probe,
    )
    recipe.write_text(
        "require fastmcp\nserver probe_gway_mutation\n",
        encoding="utf-8",
    )
    gateway.ingest(root)

    with gateway.authorized(
        operations={"mcpgwaymutating.server", "mutate_now"}
    ):
        result = gateway("mcpgwaymutating server")

    assert result == "done"
    assert seen == ["mutated"]
