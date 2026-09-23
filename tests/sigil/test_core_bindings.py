import pytest

from gway import Gateway


@pytest.mark.parametrize(
    "environment, expected",
    [
        (
            {
                "GWAY_REMOTE_MCP_ENDPOINT": "https://joint.example/mcp",
                "GWAY_MCP_ENDPOINT": "https://mcp.example/mcp",
                "GWAY_REMOTE_ENDPOINT": "https://remote.example",
            },
            "https://joint.example/mcp",
        ),
        (
            {
                "GWAY_MCP_ENDPOINT": "https://mcp.example/mcp",
                "GWAY_REMOTE_ENDPOINT": "https://remote.example",
            },
            "https://mcp.example/mcp",
        ),
        (
            {"GWAY_REMOTE_ENDPOINT": "https://remote.example"},
            "https://remote.example",
        ),
    ],
)
def test_remote_mcp_endpoint_follows_semantic_specificity(
    monkeypatch,
    environment,
    expected,
):
    for name in (
        "GWAY_REMOTE_MCP_ENDPOINT",
        "GWAY_MCP_ENDPOINT",
        "GWAY_REMOTE_ENDPOINT",
    ):
        monkeypatch.delenv(name, raising=False)
    for name, value in environment.items():
        monkeypatch.setenv(name, value)

    gateway = Gateway()

    with gateway.topics("remote", "mcp"):
        assert gateway.resolve("[endpoint]") == expected


def test_remote_mcp_topic_order_is_equivalent(monkeypatch):
    monkeypatch.setenv("GWAY_REMOTE_MCP_PUBLIC_ORIGIN", "https://joint.example")

    gateway = Gateway()

    with gateway.topics("mcp", "remote"):
        assert gateway.resolve("[public_origin]") == "https://joint.example"
