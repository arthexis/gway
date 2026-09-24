import sqlite3

from gway.security.oauth import OAuthClient, OAuthRegistry


def test_oauth_client_management_round_trips_safe_metadata(tmp_path):
    oauth = OAuthRegistry(tmp_path / "security.sqlite")

    issued = oauth.create_client(
        "mcp-confidential-client",
        redirect_uris={"https://chatgpt.com/callback"},
        confidential=True,
        token_endpoint_auth_method="client_secret_post",
    )

    shown = oauth.require_client("mcp-confidential-client")
    listed = oauth.clients()

    assert shown == issued.client
    assert listed == [shown]
    assert shown.token_endpoint_auth_method == "client_secret_post"
    assert not hasattr(shown, "client_secret")

    assert oauth.disable_client("mcp-confidential-client").disabled is True
    assert oauth.enable_client("mcp-confidential-client").disabled is False
    assert oauth.remove_client("mcp-confidential-client") is True
    assert oauth.get_client("mcp-confidential-client") is None


def test_oauth_client_secret_never_appears_in_safe_metadata(tmp_path):
    oauth = OAuthRegistry(tmp_path / "security.sqlite")

    issued = oauth.create_client(
        "mcp-confidential-client",
        redirect_uris={"https://chatgpt.com/callback"},
        confidential=True,
    )

    assert issued.client_secret not in repr(oauth.require_client("mcp-confidential-client"))
    assert issued.client_secret not in repr(oauth.clients())

    with sqlite3.connect(oauth.path) as connection:
        dump = "\n".join(connection.iterdump())
    assert issued.client_secret not in dump


def test_security_oauth_client_gway_command_surface(gateway, tmp_path):
    gateway.cache.root = tmp_path
    gateway.security_path = tmp_path / "security.sqlite"

    secret = gateway(
        "security oauth client create mcp-confidential-client "
        "https://chatgpt.com/callback "
        "--confidential --method client_secret_post"
    )

    assert secret.startswith("gwcs_")

    shown = gateway("security oauth client show mcp-confidential-client")
    assert isinstance(shown, OAuthClient)
    assert shown.client_id == "mcp-confidential-client"
    assert shown.redirect_uris == frozenset({"https://chatgpt.com/callback"})
    assert shown.token_endpoint_auth_method == "client_secret_post"
    assert secret not in repr(shown)

    listed = gateway("security oauth client list")
    assert listed == [shown]
    assert secret not in repr(listed)

    assert gateway("security oauth client disable mcp-confidential-client").disabled is True
    assert gateway("security oauth client enable mcp-confidential-client").disabled is False
    assert gateway("security oauth client delete mcp-confidential-client") is True


def test_security_oauth_client_reads_support_forced_non_mutation(
    gateway,
    tmp_path,
):
    gateway.cache.root = tmp_path
    gateway.security_path = tmp_path / "security.sqlite"
    oauth = OAuthRegistry(gateway.security_path)
    oauth.create_client(
        "public-client",
        redirect_uris={"https://client.example/callback"},
    )
    before = oauth.path.read_bytes()

    shown = gateway.execute(
        "security oauth client show public-client",
        mutate=False,
    )
    listed = gateway.execute(
        "security oauth client list",
        mutate=False,
    )

    assert shown.client_id == "public-client"
    assert listed == [shown]
    assert oauth.path.read_bytes() == before


def test_security_oauth_client_commands_share_gateway_security_path(gateway, tmp_path):
    gateway.cache.root = tmp_path / "cache"
    gateway.security_path = gateway.cache.root / "security" / "state.sqlite"

    secret = gateway(
        "security oauth client create actions-client "
        "https://chatgpt.com/callback "
        "--confidential --method client_secret_post"
    )

    assert secret.startswith("gwcs_")
    registered = OAuthRegistry(gateway.security_path).require_client("actions-client")
    assert registered.client_id == "actions-client"
    assert registered.redirect_uris == frozenset({"https://chatgpt.com/callback"})
