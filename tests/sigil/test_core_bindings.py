from gway import Gateway


def test_remote_mcp_endpoint_prefers_joint_topic_binding(monkeypatch):
    monkeypatch.setenv("GWAY_REMOTE_MCP_ENDPOINT", "https://joint.example/mcp")
    monkeypatch.setenv("GWAY_MCP_ENDPOINT", "https://mcp.example/mcp")
    monkeypatch.setenv("GWAY_REMOTE_ENDPOINT", "https://remote.example")

    gateway = Gateway()

    with gateway.topics("remote", "mcp"):
        assert gateway.resolve("[endpoint]") == "https://joint.example/mcp"


def test_remote_mcp_endpoint_falls_back_to_mcp_topic(monkeypatch):
    monkeypatch.delenv("GWAY_REMOTE_MCP_ENDPOINT", raising=False)
    monkeypatch.setenv("GWAY_MCP_ENDPOINT", "https://mcp.example/mcp")
    monkeypatch.setenv("GWAY_REMOTE_ENDPOINT", "https://remote.example")

    gateway = Gateway()

    with gateway.topics("remote", "mcp"):
        assert gateway.resolve("[endpoint]") == "https://mcp.example/mcp"


def test_remote_mcp_endpoint_falls_back_to_remote_topic(monkeypatch):
    monkeypatch.delenv("GWAY_REMOTE_MCP_ENDPOINT", raising=False)
    monkeypatch.delenv("GWAY_MCP_ENDPOINT", raising=False)
    monkeypatch.setenv("GWAY_REMOTE_ENDPOINT", "https://remote.example")

    gateway = Gateway()

    with gateway.topics("remote", "mcp"):
        assert gateway.resolve("[endpoint]") == "https://remote.example"


def test_remote_mcp_topic_order_is_equivalent(monkeypatch):
    monkeypatch.setenv("GWAY_REMOTE_MCP_PUBLIC_ORIGIN", "https://joint.example")

    gateway = Gateway()

    with gateway.topics("mcp", "remote"):
        assert gateway.resolve("[public_origin]") == "https://joint.example"
