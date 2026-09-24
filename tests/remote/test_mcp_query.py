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
            return tools, query, safe, generic

    tools, query, safe, generic = asyncio.run(run())

    assert [tool.name for tool in tools] == ["gway", "query"]
    gway = next(tool for tool in tools if tool.name == "gway")
    assert query.annotations.readOnlyHint is True
    assert query.annotations.destructiveHint is False
    assert query.annotations.openWorldHint is True
    assert gway.annotations.readOnlyHint is False
    assert gway.annotations.destructiveHint is True
    assert gway.annotations.openWorldHint is True

    assert query.outputSchema is not None
    assert gway.outputSchema is not None
    assert set(query.outputSchema["required"]) == {
        "ok",
        "result",
        "result_type",
        "output",
    }

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
    assert parent.calls == [
        ("observe", False),
        ("restart", None),
    ]



def test_mcp_execution_envelope_classifies_json_result_shapes():
    server = _server_module()

    assert server._envelope({"a": 1}).model_dump() == {
        "ok": True,
        "result": {"a": 1},
        "result_type": "mapping",
        "output": [],
    }
    assert server._envelope([1, 2]).result_type == "sequence"
    assert server._envelope(3.5).result_type == "number"
    assert server._envelope(True).result_type == "boolean"
    assert server._envelope(None).result_type == "null"
