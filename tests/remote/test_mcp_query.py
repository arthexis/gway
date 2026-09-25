import asyncio
import importlib.util

from fastmcp import Client

from gway.sampler import root as sampler_root


def _server_module():
    path = sampler_root() / "mcp" / "server.py"
    spec = importlib.util.spec_from_file_location("_gway_audit_mcp_server", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Parent:
    def __init__(self):
        self.calls = []

    def execute(self, command, mutate=None):
        self.calls.append((command, mutate))
        if command == "one ; two":
            return {
                "results": [
                    {"subject": "one", "result": 1},
                    {"subject": "two", "result": 2},
                ]
            }
        return f"{command}:{mutate}"


def test_mcp_query_projection_is_read_only_in_active_pr_suite():
    server = _server_module()
    parent = Parent()
    server._gway_parent = parent

    async def run():
        async with Client(server.mcp) as client:
            tools = await client.list_tools()
            query = next(tool for tool in tools if tool.name == "query")
            safe = await client.call_tool("query", {"command": "observe"})
            generic = await client.call_tool("gway", {"command": "restart"})
            query_aggregate = await client.call_tool(
                "query",
                {"command": "one ; two"},
            )
            gway_aggregate = await client.call_tool(
                "gway",
                {"command": "one ; two"},
            )
            return tools, query, safe, generic, query_aggregate, gway_aggregate

    tools, query, safe, generic, query_aggregate, gway_aggregate = asyncio.run(run())

    assert [tool.name for tool in tools] == ["gway", "query"]
    gway = next(tool for tool in tools if tool.name == "gway")
    assert query.annotations.read_only_hint is True
    assert query.annotations.destructive_hint is False
    assert query.annotations.open_world_hint is True
    assert gway.annotations.read_only_hint is False
    assert gway.annotations.destructive_hint is True
    assert gway.annotations.open_world_hint is True
    assert "observation and diagnosis" in query.description
    assert "semicolons" in query.description
    assert "guide <task>" in query.description
    assert "help <operation>" in query.description
    assert "mutation is required" in gway.description
    assert "semicolons" in gway.description
    assert "investigate through query first" in gway.description

    assert query.output_schema is not None
    assert gway.output_schema is not None
    assert set(query.output_schema["required"]) == {
        "ok",
        "result",
        "result_type",
        "output",
    }

    assert safe.content[0].text == "observe:False"
    assert generic.content[0].text == "restart:None"
    assert safe.structured_content == {
        "ok": True,
        "result": "observe:False",
        "result_type": "string",
        "output": [],
    }
    assert generic.structured_content == {
        "ok": True,
        "result": "restart:None",
        "result_type": "string",
        "output": [],
    }
    expected_aggregate = {
        "results": [
            {"subject": "one", "result": 1},
            {"subject": "two", "result": 2},
        ]
    }
    assert query_aggregate.structured_content == {
        "ok": True,
        "result": expected_aggregate,
        "result_type": "mapping",
        "output": [],
    }
    assert gway_aggregate.structured_content == {
        "ok": True,
        "result": expected_aggregate,
        "result_type": "mapping",
        "output": [],
    }
    assert parent.calls == [
        ("observe", False),
        ("restart", None),
        ("one ; two", False),
        ("one ; two", None),
    ]



def test_mcp_tools_expose_real_gateway_multi_statement_results(gateway):
    server = _server_module()

    def observe_alpha(*, mutate=False):
        return f"A:{mutate}"

    def observe_beta(*, mutate=False):
        return f"B:{mutate}"

    gateway.first = gateway.wrap("read_alpha", observe_alpha)
    gateway.second = gateway.wrap("read_beta", observe_beta)
    server._gway_parent = gateway

    async def run():
        async with Client(server.mcp) as client:
            query_result = await client.call_tool(
                "query",
                {"command": "first ; second"},
            )
            gway_result = await client.call_tool(
                "gway",
                {"command": "first ; second"},
            )
            return query_result, gway_result

    query_result, gway_result = asyncio.run(run())

    assert query_result.structured_content["result"] == {
        "results": [
            {"subject": "alpha", "result": "A:False"},
            {"subject": "beta", "result": "B:False"},
        ]
    }
    assert gway_result.structured_content["result"] == {
        "results": [
            {"subject": "alpha", "result": "A:False"},
            {"subject": "beta", "result": "B:False"},
        ]
    }


def test_mcp_gway_rechecks_each_real_multi_statement_operation(gateway):
    server = _server_module()
    calls = []

    gateway.first = gateway.wrap("read_alpha", lambda: "A")

    def second():
        calls.append("second")
        return "B"

    gateway.second = gateway.wrap("read_beta", second)
    server._gway_parent = gateway

    async def run():
        async with Client(server.mcp) as client:
            await client.call_tool(
                "gway",
                {"command": "first ; second"},
            )

    with gateway.authorized(operations={"read_alpha"}):
        try:
            asyncio.run(run())
        except Exception as exception:
            assert "Operation is not authorized: read_beta" in str(exception)
        else:
            raise AssertionError("multi-statement authorization unexpectedly succeeded")

    assert calls == []


def test_mcp_execution_envelope_classifies_json_result_shapes():
    server = _server_module()

    assert server._envelope({"a": 1}) == {
        "ok": True,
        "result": {"a": 1},
        "result_type": "mapping",
        "output": [],
    }
    assert server._envelope([1, 2])["result_type"] == "sequence"
    assert server._envelope(3.5)["result_type"] == "number"
    assert server._envelope(True)["result_type"] == "boolean"
    assert server._envelope(None)["result_type"] == "null"
