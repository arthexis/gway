from pathlib import Path
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
    monkeypatch.setattr(companion_runtime, "TokenRegistry", lambda path=None: tokens)
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
        result = gateway("mcp server")

    assert result.content[0].text == "hello!"
    assert result.structured_content["result"] == "hello!"


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



def test_mcp_stdio_transport_lists_tools_and_survives_authorization_error(
    gateway, recipe_factory, required_runtime, tmp_path
):
    root = tmp_path / "mcpstdio"
    mutations = []

    def mutate_now():
        mutations.append("mutated")
        return "done"

    gateway.allowed = gateway.wrap("allowed", lambda: "ok")
    gateway.denied = gateway.wrap("denied", lambda: "no")
    gateway.mutate_now = gateway.wrap("mutate_now", mutate_now)
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
        "                tools = [tool.name for tool in await client.list_tools()]\n"
        "                first = await client.call_tool('gway', {'command': 'allowed'})\n"
        "                error = None\n"
        "                try:\n"
        "                    await client.call_tool('gway', {'command': 'denied'})\n"
        "                except Exception as exception:\n"
        "                    error = str(exception)\n"
        "                second = await client.call_tool('gway', {'command': 'allowed'})\n"
        "                mutated = await client.call_tool('gway', {'command': 'mutate_now'})\n"
        "                return tools, first.content[0].text, error, second.content[0].text, mutated.content[0].text\n"
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

    with gateway.authorized(
        operations={"mcpstdio.server", "allowed", "mutate_now"}
    ):
        tools, first, error, second, mutated = gateway("mcpstdio server")

    assert tools == ["gway", "query", "tail"]
    assert first == "ok"
    assert "Operation is not authorized: denied" in error
    assert second == "ok"
    assert mutated == "done"
    assert mutations == ["mutated"]


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
    monkeypatch.setattr(companion_runtime, "TokenRegistry", lambda path=None: tokens)

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
    monkeypatch.setattr(companion_runtime, "TokenRegistry", lambda path=None: tokens)

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

    async def call_pair(url, credential, first_value, second_value):
        auth = None if credential == "__missing__" else BearerAuth(credential)
        try:
            async with Client(url, auth=auth) as client:
                tools = [tool.name for tool in await client.list_tools()]
                results = []
                for value in (first_value, second_value):
                    try:
                        result = await client.call_tool(tool, {"command": value})
                    except Exception as exception:
                        results.append((tools, None, str(exception)))
                    else:
                        results.append((tools, result.content[0].text, None))
                return results
        except Exception as exception:
            failure = ([], None, str(exception))
            return [failure, failure]

    async def run(url):
        if second_command is None:
            return await call(url, bearer, command)
        if second_bearer == bearer:
            return await call_pair(url, bearer, command, second_command)
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


def probe_token_http(reader_bearer, alpha_bearer, beta_bearer, invalid_bearer):
    import asyncio
    import http.client
    import json
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

    async def call(url, credential, operation):
        try:
            async with Client(url, auth=BearerAuth(credential)) as client:
                tools = await client.list_tools()
                try:
                    result = await client.call_tool(operation, {})
                except Exception as exception:
                    return [tool.name for tool in tools], None, str(exception)
                return [tool.name for tool in tools], result.content[0].text, None
        except Exception as exception:
            return [], None, str(exception)

    async def reader_calls(url):
        try:
            async with Client(url, auth=BearerAuth(reader_bearer)) as client:
                tools = [tool.name for tool in await client.list_tools()]
                allowed = await client.call_tool("allowed", {})
                try:
                    await client.call_tool("denied", {})
                except Exception as exception:
                    denied = (tools, None, str(exception))
                else:
                    denied = (tools, "no", None)
                return (tools, allowed.content[0].text, None), denied
        except Exception as exception:
            failure = ([], None, str(exception))
            return failure, failure

    async def run(url):
        allowed, denied = await reader_calls(url)
        concurrent = await asyncio.gather(
            call(url, alpha_bearer, "alpha"),
            call(url, beta_bearer, "beta"),
        )
        return allowed, denied, concurrent

    def challenge(port):
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {invalid_bearer}",
        }
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
        www_authenticate = response.getheader("WWW-Authenticate")
        response.read()
        connection.close()
        return status, www_authenticate

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
            allowed, denied, concurrent = asyncio.run(
                run(f"http://127.0.0.1:{port}/mcp")
            )
            status, www_authenticate = challenge(port)
            return allowed, denied, concurrent, status, www_authenticate
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


def test_mcp_http_token_registry_acceptance_shares_one_server(
    gateway, recipe_factory, required_runtime, tmp_path, monkeypatch
):
    path = tmp_path / "security.sqlite"
    scopes = ScopeRegistry(path)
    tokens = TokenRegistry(path)
    scopes.replace("reader", operations={"allowed"})
    scopes.replace("alpha-scope", operations={"alpha"})
    scopes.replace("beta-scope", operations={"beta"})
    reader = tokens.create("http-client", scopes={"reader"})
    alpha = tokens.create("alpha-client", scopes={"alpha-scope"})
    beta = tokens.create("beta-client", scopes={"beta-scope"})
    monkeypatch.setattr(companion_runtime, "TokenRegistry", lambda path=None: tokens)

    gateway.allowed = gateway.wrap("allowed", lambda: "ok")
    gateway.denied = gateway.wrap("denied", lambda: "no")
    gateway.alpha = gateway.wrap("alpha", lambda: "alpha-ok")
    gateway.beta = gateway.wrap("beta", lambda: "beta-ok")

    recipe = _mcp_http_recipe(recipe_factory, tmp_path / "mcphttp")
    recipe.write_text(
        "require fastmcp\n"
        f"server probe token http {reader.bearer!r} {alpha.bearer!r} "
        f"{beta.bearer!r} gwt_missing_wrong\n",
        encoding="utf-8",
    )
    gateway.ingest(recipe.parent)

    with gateway.authorized(operations={"mcphttp.server"}):
        allowed, denied, concurrent, status, challenge = gateway("mcphttp server")

    assert allowed == (["allowed"], "ok", None)
    assert denied[0] == ["allowed"]
    assert denied[1] is None
    assert "not authorized" in denied[2]
    assert "Invalid bearer token" not in denied[2]

    assert concurrent == [
        (["alpha"], "alpha-ok", None),
        (["beta"], "beta-ok", None),
    ]

    assert status == 401
    assert challenge.startswith("Bearer")
    assert (
        'resource_metadata="'
        "https://remote.example.test/.well-known/oauth-protected-resource/mcp"
        '"' in challenge
    )



def _issued_oauth_acceptance_tokens(tmp_path, monkeypatch):
    path = tmp_path / "security.sqlite"
    scopes = ScopeRegistry(path)
    tokens = TokenRegistry(path)
    oauth = OAuthRegistry(path)

    scopes.replace("reader", operations={"allowed"})
    scopes.replace(
        "chatgpt-logs",
        operations={"log.sources", "log.read", "log.tail", "log.search"},
        environment=(),
    )
    tokens.create("operator", scopes={"reader"})
    tokens.create("chatgpt-operator", scopes={"chatgpt-logs"})
    oauth.link("chatgpt-reader", "operator")
    oauth.link("chatgpt-logs", "chatgpt-operator")

    reader_grant = oauth.create_grant(
        "chatgpt-reader",
        "chatgpt-client",
        scopes={"reader"},
        resource=MCP_RESOURCE,
    )
    logs_grant = oauth.create_grant(
        "chatgpt-logs",
        "chatgpt-client",
        scopes={"chatgpt-logs"},
        resource=MCP_RESOURCE,
    )
    reader = oauth.issue_tokens(reader_grant.id)
    logs = oauth.issue_tokens(logs_grant.id)
    monkeypatch.setattr(companion_runtime, "OAuthRegistry", lambda path=None: oauth)
    return reader, logs


def _mcp_oauth_http_probe_suffix():
    return r'''
def probe_oauth_http(reader_bearer, logs_bearer):
    import asyncio
    import json
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

    async def reader_calls(url):
        async with Client(url, auth=BearerAuth(reader_bearer)) as client:
            tools = [tool.name for tool in await client.list_tools()]
            allowed = await client.call_tool("allowed", {})
            try:
                await client.call_tool("clear", {})
            except Exception as exception:
                denied = (tools, None, str(exception))
            else:
                denied = (tools, "unexpected", None)
            return (tools, allowed.content[0].text, None), denied

    async def log_query(url):
        async with Client(url, auth=BearerAuth(logs_bearer)) as client:
            tools = [tool.name for tool in await client.list_tools()]
            result = await client.call_tool(
                "log.search",
                {"tokens": ["timeout", "arthexis", "--limit", "10"]},
            )
            return tools, json.loads(result.content[0].text)

    async def run(url):
        return await asyncio.gather(reader_calls(url), log_query(url))

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


def test_mcp_oauth_http_acceptance_shares_one_server(
    gateway, recipe_factory, required_runtime, tmp_path, monkeypatch
):
    reader, logs = _issued_oauth_acceptance_tokens(tmp_path, monkeypatch)
    _install_log_acceptance_fixture(tmp_path, monkeypatch)

    gateway.allowed = gateway.wrap("allowed", lambda: "ok")
    root = tmp_path / "mcpoauth"
    recipe = _mcp_companion_recipe(
        recipe_factory,
        root,
        "clear",
        suffix=_mcp_oauth_http_probe_suffix(),
    )
    recipe.write_text(
        "require fastmcp\n"
        f"server probe_oauth_http {reader.access_token!r} {logs.access_token!r}\n",
        encoding="utf-8",
    )
    gateway.ingest(root)

    with gateway.authorized(operations={"mcpoauth.server"}):
        reader_result, log_result = gateway("mcpoauth server")

    allowed, trusted_only = reader_result
    assert allowed == (["allowed"], "ok", None)
    assert trusted_only[0] == ["allowed"]
    assert trusted_only[1] is None
    assert "not authorized" in trusted_only[2]
    assert "401" not in trusted_only[2]

    tools, result = log_result
    assert tools == ["log.read", "log.search", "log.sources", "log.tail"]
    assert [item["message"] for item in result] == ["timeout waiting for charger"]
    assert "GWAY_SECRET" not in repr(result)


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



def test_mcp_semantic_surface_is_not_eagerly_registered(gateway):
    assert gateway.ops.resolve("mcp.local") is None
    assert gateway.ops.resolve("mcp.serve") is None


def test_mcp_sampler_fallback_registers_semantic_surface(gateway, monkeypatch):
    import gway.sampler as sampler

    calls = []

    def fake_run(runtime, recipe_name, **context):
        calls.append((runtime, recipe_name, context))
        return {"recipe": recipe_name, "context": context}

    monkeypatch.setattr(sampler, "run", fake_run)

    loaded_mcp = sampler.load("mcp")
    monkeypatch.setattr(loaded_mcp, "_run_local", lambda runtime: "local")

    result = gateway("mcp local")

    assert result == "local"
    assert calls == []
    assert gateway.ops.resolve("mcp.local") is not None
    assert gateway.ops.resolve("mcp.serve") is not None


def test_mcp_semantic_serve_hides_transport_detail(gateway, monkeypatch):
    import gway.sampler as sampler

    calls = []

    def fake_run(runtime, recipe_name, **context):
        calls.append((runtime, recipe_name, context))
        return context

    monkeypatch.setattr(sampler, "run", fake_run)

    result = gateway(
        "mcp serve --host 127.0.0.2 --port 8123 "
        "--route /agent-mcp --endpoint http://127.0.0.2:8123/agent-mcp"
    )

    assert result == {
        "host": "127.0.0.2",
        "port": 8123,
        "route": "/agent-mcp",
        "endpoint": "http://127.0.0.2:8123/agent-mcp",
    }
    assert calls == [(gateway, "mcp/serve", result)]


def test_mcp_server_is_compatibility_alias_for_serve(gateway, monkeypatch):
    import gway.sampler as sampler

    monkeypatch.setattr(
        sampler,
        "run",
        lambda runtime, recipe_name, **context: recipe_name,
    )

    assert gateway("mcp server") == "mcp/serve"


def test_mcp_help_discovers_sampler_namespace(gateway):
    local = gateway._help("mcp", "local", verbose=True)

    assert "command: gway" in local
    assert 'args: ["mcp", "local"]' in local
    assert gateway.ops.resolve("mcp.local") is not None


def test_mcp_semantic_recipes_are_maintained_sampler_entries():
    from gway.sampler import recipes

    available = set(recipes())

    assert "mcp/local" in available
    assert "mcp/serve" in available


def test_mcp_local_recipe_is_semantic_alias():
    recipe = (sampler_root() / "mcp" / "local.rx").read_text(encoding="utf-8")

    assert recipe == "mcp local\n"


def test_mcp_serve_recipe_reuses_shared_server_with_loopback_defaults():
    recipe = (sampler_root() / "mcp" / "serve.rx").read_text(encoding="utf-8")
    companion = (sampler_root() / "mcp" / "serve.py").read_text(encoding="utf-8")

    assert "[host|127.0.0.1]" in recipe
    assert "[port|8000]" in recipe
    assert "[route|/mcp]" in recipe
    assert 'with_name("server.py")' in companion
    assert "_server().serve(" in companion


def test_mcp_server_companion_does_not_import_host_gway_package():
    source = Path("sampler/mcp/server.py").read_text(encoding="utf-8")

    assert "from gway." not in source
    assert "import gway" not in source
    assert "_tail_fingerprint" in source
    assert "_tail_terminal" in source
