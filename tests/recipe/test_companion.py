import os

import pytest

from gway.recipe import companion as companion_runtime
from gway.sampler import root as sampler_root
from gway.security.scopes import ScopeRegistry
from gway.security.tokens import TokenRegistry


def test_recipe_ingests_same_stem_companion_before_resolution(
    gateway, recipe_factory
):
    recipe = recipe_factory(
        name="deploy",
        body="deploy prepare charger\n",
        companion=(
            "def prepare(name):\n"
            "    return f'prepared:{name}'\n"
        ),
    )

    assert gateway(recipe) == "prepared:charger"
    assert gateway.ops.resolve("deploy.prepare") is not None


def test_companion_is_resolved_from_recipe_directory_not_cwd(
    gateway, recipe_factory, tmp_path, monkeypatch
):
    root = tmp_path / "recipes"
    recipe = recipe_factory(
        name="status",
        root=root,
        body="status read\n",
        companion="def read():\n    return 'recipe-dir'\n",
    )
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "status.py").write_text(
        "def read():\n    return 'cwd'\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(elsewhere)

    assert gateway(recipe) == "recipe-dir"


def test_companion_is_ingested_once_per_gateway(
    gateway, recipe_factory, tmp_path
):
    marker = tmp_path / "imports.txt"
    recipe = recipe_factory(
        name="once",
        body="once run\n",
        companion=(
            "from pathlib import Path\n"
            f"_marker = Path({str(marker)!r})\n"
            "_marker.write_text("
            "_marker.read_text() + 'x' if _marker.exists() else 'x'"
            ")\n"
            "def run():\n"
            "    return 'ok'\n"
        ),
    )

    assert gateway(recipe) == "ok"
    assert gateway(recipe) == "ok"
    assert marker.read_text(encoding="utf-8") == "x"


def test_nested_recipe_loads_its_own_companion(gateway, recipe_factory):
    inner = recipe_factory(
        "inner",
        "inner ping\n",
        companion="def ping():\n    return 'pong'\n",
    )
    outer = recipe_factory("outer", "./inner.rx\n")

    assert gateway(outer) == "pong"
    assert inner.is_file()


def test_failed_companion_import_prevents_recipe_execution(
    gateway, recipe_factory
):
    recipe = recipe_factory(
        name="broken",
        body="clear\n",
        companion="raise RuntimeError('companion boom')\n",
    )

    with pytest.raises(RuntimeError, match="companion boom"):
        gateway(recipe)


def test_required_companion_namespace_is_hidden_until_require_passes(
    gateway, recipe_factory, required_runtime
):
    recipe = recipe_factory(
        body="demo ping\nrequire placeholder\n",
        companion="def ping():\n    return 'pong'\n",
    )

    with pytest.raises(LookupError, match="Unable to resolve operation"):
        gateway(recipe)

    assert gateway.ops.resolve("demo.ping") is None


def test_require_unlocks_managed_companion_namespace(
    gateway, recipe_factory, required_runtime
):
    recipe = recipe_factory(
        body="require placeholder\ndemo ping hello\n",
        companion=(
            "def ping(value='pong'):\n"
            "    return value\n"
        ),
    )

    assert gateway(recipe) == "hello"
    assert gateway.ops.resolve("demo.ping") is None


def test_require_can_unlock_companion_in_same_pipeline(
    gateway, recipe_factory, required_runtime
):
    recipe = recipe_factory(
        body="require placeholder - demo ping\n",
        companion="def ping():\n    return 'pong'\n",
    )

    assert gateway(recipe) == "pong"


def test_managed_companion_runs_in_separate_process(
    gateway, recipe_factory, required_runtime
):
    recipe = recipe_factory(
        body="require placeholder\ndemo pid\n",
        companion=(
            "import os\n"
            "def pid():\n"
            "    return os.getpid()\n"
        ),
    )

    assert gateway(recipe) != os.getpid()


def test_managed_companion_can_list_describe_and_call_parent_gateway(
    gateway, recipe_factory, required_runtime
):
    def add(a, b):
        """Add two values in the authoritative parent Gateway."""
        return a + b

    gateway.wrap("add", add)
    recipe = recipe_factory(
        body="require placeholder\ndemo probe\n",
        companion=(
            "def probe():\n"
            "    operations = _gway_parent.list_operations()\n"
            "    description = _gway_parent.describe_operation('add')\n"
            "    result = _gway_parent.call_operation('add', 2, 3)\n"
            "    return {\n"
            "        'listed': 'add' in operations,\n"
            "        'name': description['name'],\n"
            "        'parameters': [p['name'] for p in description['parameters']],\n"
            "        'result': result,\n"
            "    }\n"
        ),
    )

    assert gateway(recipe) == {
        "listed": True,
        "name": "add",
        "parameters": ["a", "b"],
        "result": 5,
    }


def test_parent_gateway_rpc_error_does_not_desynchronize_companion(
    gateway, recipe_factory, required_runtime
):
    def add(a, b):
        return a + b

    def explode():
        raise ValueError("boom")

    gateway.wrap("add", add)
    gateway.wrap("explode", explode)
    recipe = recipe_factory(
        body="require placeholder\ndemo recover\n",
        companion=(
            "def recover():\n"
            "    try:\n"
            "        _gway_parent.call_operation('explode')\n"
            "    except RuntimeError as exception:\n"
            "        failed = 'ValueError: boom' in str(exception)\n"
            "    else:\n"
            "        failed = False\n"
            "    return failed, _gway_parent.call_operation('add', 2, 3)\n"
        ),
    )

    assert gateway(recipe) == (True, 5)



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
        "        with _callback_relay() as env:\n"
        "            transport = PythonStdioTransport(str(Path(__file__)), env=env)\n"
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

    assert tools == ["gway"]
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
        "        with _callback_relay() as env:\n"
        "            transport = PythonStdioTransport(str(Path(__file__)), env=env)\n"
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
    path = tmp_path / "security.sqlite"
    scopes = ScopeRegistry(path)
    tokens = TokenRegistry(path)
    scopes.replace("reader", operations={"allowed"})
    issued = tokens.create("client", scopes={"reader"})
    monkeypatch.setattr(companion_runtime, "TokenRegistry", lambda: tokens)

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
    path = tmp_path / "security.sqlite"
    scopes = ScopeRegistry(path)
    tokens = TokenRegistry(path)
    scopes.replace("reader", operations={"allowed"})
    issued = tokens.create("client", scopes={"reader"})
    tokens.disable("client")
    monkeypatch.setattr(companion_runtime, "TokenRegistry", lambda: tokens)

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
def probe_http(bearer, command, second_bearer=None, second_command=None):
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
        auth = None if credential is None else BearerAuth(credential)
        async with Client(url, auth=auth) as client:
            tools = await client.list_tools()
            try:
                result = await client.call_tool("gway", {"command": value})
            except Exception as exception:
                return [tool.name for tool in tools], None, str(exception)
            return [tool.name for tool in tools], result.content[0].text, None

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
    with _callback_relay() as callback_env:
        env = os.environ.copy()
        env.update(callback_env)
        process = subprocess.Popen(
            [
                sys.executable,
                str(Path(__file__)),
                "--transport",
                "http",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--path",
                "/mcp",
            ],
            env=env,
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
    path = tmp_path / "security.sqlite"
    scopes = ScopeRegistry(path)
    tokens = TokenRegistry(path)
    scopes.replace("reader", operations={"allowed"})
    issued = tokens.create("http-client", scopes={"reader"})
    monkeypatch.setattr(companion_runtime, "TokenRegistry", lambda: tokens)

    gateway.allowed = gateway.wrap("allowed", lambda: "ok")
    recipe = _mcp_http_recipe(recipe_factory, tmp_path / "mcphttp")
    recipe.write_text(
        f"require fastmcp\nserver probe http {issued.bearer!r} allowed\n",
        encoding="utf-8",
    )
    gateway.ingest(recipe.parent)

    with gateway.authorized(operations={"mcphttp.server"}):
        tools, result, error = gateway("mcphttp server")

    assert tools == ["gway"]
    assert result == "ok"
    assert error is None


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

    assert tools == ["gway"]
    assert result is None
    assert "Operation is not authorized: denied" in error
    assert "Invalid bearer token" not in error


@pytest.mark.parametrize("credential", [None, "gwt_missing_wrong"])
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
        tmp_path / ("mcphttpmissing" if credential is None else "mcphttpinvalid"),
    )
    value = "None" if credential is None else repr(credential)
    recipe.write_text(
        f"require fastmcp\nserver probe http {value} clear\n",
        encoding="utf-8",
    )
    gateway.ingest(recipe.parent)

    operation = recipe.parent.name.replace("-", "_") + ".server"
    with gateway.authorized(operations={operation}):
        tools, result, error = gateway(operation.replace(".", " "))

    assert tools == ["gway"]
    assert result is None
    if credential is None:
        assert "Bearer authentication required" in error
    else:
        assert "Invalid bearer token" in error


def test_mcp_http_rejects_disabled_bearer(
    gateway, recipe_factory, required_runtime, tmp_path, monkeypatch
):
    path = tmp_path / "security.sqlite"
    scopes = ScopeRegistry(path)
    tokens = TokenRegistry(path)
    scopes.replace("reader", operations={"allowed"})
    issued = tokens.create("http-client", scopes={"reader"})
    tokens.disable("http-client")
    monkeypatch.setattr(companion_runtime, "TokenRegistry", lambda: tokens)

    gateway.allowed = gateway.wrap("allowed", lambda: "ok")
    recipe = _mcp_http_recipe(recipe_factory, tmp_path / "mcphttpdisabled")
    recipe.write_text(
        f"require fastmcp\nserver probe http {issued.bearer!r} allowed\n",
        encoding="utf-8",
    )
    gateway.ingest(recipe.parent)

    with gateway.authorized(operations={"mcphttpdisabled.server"}):
        tools, result, error = gateway("mcphttpdisabled server")

    assert tools == ["gway"]
    assert result is None
    assert "Invalid bearer token" in error


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
        (["gway"], "alpha-ok", None),
        (["gway"], "beta-ok", None),
    ]
