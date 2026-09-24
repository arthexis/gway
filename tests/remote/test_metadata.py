import pytest

from gway.remote.metadata import RemoteOAuthMetadata


def test_remote_metadata_separates_issuer_from_mcp_resource():
    metadata = RemoteOAuthMetadata.from_origin(
        "https://remote.arthexis.com",
        resource_path="/mcp",
    )

    assert metadata.issuer == "https://remote.arthexis.com"
    assert metadata.resource == "https://remote.arthexis.com/mcp"
    assert metadata.protected_resource_metadata_path == (
        "/.well-known/oauth-protected-resource/mcp"
    )
    assert metadata.authorization_server_metadata_path == (
        "/.well-known/oauth-authorization-server"
    )


def test_protected_resource_document_points_to_shared_remote_issuer():
    metadata = RemoteOAuthMetadata.from_origin("https://remote.example.test")

    assert metadata.protected_resource_document() == {
        "resource": "https://remote.example.test/mcp",
        "authorization_servers": ["https://remote.example.test"],
        "bearer_methods_supported": ["header"],
    }


def test_authorization_server_document_advertises_only_designed_flow():
    metadata = RemoteOAuthMetadata.from_origin("https://remote.example.test")

    document = metadata.authorization_server_document()

    assert document["issuer"] == "https://remote.example.test"
    assert document["authorization_endpoint"] == (
        "https://remote.example.test/oauth/authorize"
    )
    assert document["token_endpoint"] == "https://remote.example.test/oauth/token"
    assert document["revocation_endpoint"] == (
        "https://remote.example.test/oauth/revoke"
    )
    assert document["response_types_supported"] == ["code"]
    assert document["grant_types_supported"] == [
        "authorization_code",
        "refresh_token",
    ]
    assert document["code_challenge_methods_supported"] == ["S256"]
    assert document["token_endpoint_auth_methods_supported"] == [
        "none",
        "client_secret_post",
        "client_secret_basic",
    ]
    assert document["client_id_metadata_document_supported"] is True
    assert document["protected_resources"] == [
        "https://remote.example.test/mcp"
    ]
    assert "registration_endpoint" not in document


@pytest.mark.parametrize(
    "origin",
    [
        "http://remote.example.test",
        "https://user@remote.example.test",
        "https://remote.example.test/path",
        "https://remote.example.test?query=yes",
        "https://remote.example.test#fragment",
        "not-a-url",
    ],
)
def test_public_issuer_rejects_unsafe_or_non_origin_urls(origin):
    with pytest.raises(ValueError):
        RemoteOAuthMetadata.from_origin(origin)


def test_insecure_loopback_is_available_only_for_explicit_tests():
    with pytest.raises(ValueError, match="HTTPS"):
        RemoteOAuthMetadata.from_origin("http://127.0.0.1:8765")

    metadata = RemoteOAuthMetadata.from_origin(
        "http://127.0.0.1:8765",
        allow_insecure_loopback=True,
    )

    assert metadata.issuer == "http://127.0.0.1:8765"


def test_resource_path_is_normalized_but_must_be_non_empty():
    metadata = RemoteOAuthMetadata.from_origin(
        "https://remote.example.test/",
        resource_path="mcp/",
    )
    assert metadata.resource == "https://remote.example.test/mcp"

    with pytest.raises(ValueError, match="non-empty"):
        RemoteOAuthMetadata.from_origin(
            "https://remote.example.test",
            resource_path="/",
        )
