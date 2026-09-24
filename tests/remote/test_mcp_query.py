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
    assert query.annotations.readOnlyHint is True
    assert safe.content[0].text == "observe:False"
    assert generic.content[0].text == "restart:None"
    assert parent.calls == [
        ("observe", False),
        ("restart", None),
    ]
