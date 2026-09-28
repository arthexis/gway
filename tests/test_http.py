import httpx
import pytest

from gway.http import HTTPTransportError, request


def mock(handler):
    return httpx.MockTransport(handler)


def test_request_returns_stable_json_response():
    transport = mock(
        lambda request: httpx.Response(
            200,
            json={"ready": True},
            headers={"X-Test": "yes"},
            request=request,
        )
    )

    result = request("GET", "https://example.test/status", transport=transport).result()

    assert result["status"] == 200
    assert result["url"] == "https://example.test/status"
    assert result["headers"]["x-test"] == "yes"
    assert result["result"] == {"ready": True}


def test_request_preserves_non_json_text():
    transport = mock(
        lambda request: httpx.Response(200, text="ready", request=request)
    )

    result = request("GET", "https://example.test/status", transport=transport).result()

    assert result["result"] == "ready"


def test_request_does_not_leak_authorization_header():
    def fail(request):
        raise httpx.ConnectError("secret transport detail", request=request)

    with pytest.raises(HTTPTransportError) as captured:
        request(
            "GET",
            "https://example.test/status",
            headers={"Authorization": "Bearer secret", "X-Test": "visible"},
            transport=mock(fail),
        )

    message = str(captured.value)
    assert "secret" not in message
    assert "Bearer" not in message
    assert "Authorization" in message
    assert "X-Test" in message
    assert "visible" not in message


def test_request_redirect_policy_is_explicit():
    def handler(request):
        if request.url.path == "/start":
            return httpx.Response(
                302,
                headers={"Location": "/final"},
                request=request,
            )
        return httpx.Response(200, text="done", request=request)

    transport = mock(handler)

    stopped = request(
        "GET",
        "https://example.test/start",
        transport=transport,
    )
    followed = request(
        "GET",
        "https://example.test/start",
        follow_redirects=True,
        transport=transport,
    )

    assert stopped.status == 302
    assert followed.status == 200
    assert followed.text == "done"



def test_request_error_redacts_url_credentials_query_and_custom_header_values():
    def fail(request):
        raise httpx.ConnectError("failed", request=request)

    with pytest.raises(HTTPTransportError) as captured:
        request(
            "GET",
            "https://user:password@example.test/status?token=query-secret",
            headers={"X-Api-Key": "header-secret", "X-Trace": "trace-secret"},
            transport=mock(fail),
        )

    message = str(captured.value)
    assert "user" not in message
    assert "password" not in message
    assert "query-secret" not in message
    assert "header-secret" not in message
    assert "trace-secret" not in message
    assert "https://example.test/status" in message


def test_public_result_redacts_sensitive_response_headers():
    transport = mock(
        lambda request: httpx.Response(
            200,
            text="ok",
            headers={
                "Set-Cookie": "session=secret",
                "X-Auth-Token": "response-secret",
                "X-Request-Id": "request-123",
            },
            request=request,
        )
    )

    response = request("GET", "https://example.test/status", transport=transport)
    result = response.result()

    assert response.headers["set-cookie"] == "session=secret"
    assert result["headers"]["set-cookie"] == "<redacted>"
    assert result["headers"]["x-auth-token"] == "<redacted>"
    assert result["headers"]["x-request-id"] == "request-123"


def test_request_forwards_params_json_and_timeout():
    observed = {}

    def handler(request):
        observed["url"] = str(request.url)
        observed["body"] = request.content
        observed["timeout"] = request.extensions["timeout"]["read"]
        return httpx.Response(201, json={"ok": True}, request=request)

    result = request(
        "POST",
        "https://example.test/items",
        params={"page": 2},
        json={"name": "Ada"},
        timeout=7,
        transport=mock(handler),
    )

    assert observed["url"] == "https://example.test/items?page=2"
    assert observed["body"] == b'{"name":"Ada"}'
    assert observed["timeout"] == 7
    assert result.status == 201


def test_empty_response_is_valid():
    transport = mock(
        lambda request: httpx.Response(204, content=b"", request=request)
    )

    response = request(
        "DELETE",
        "https://example.test/item",
        transport=transport,
    )
    result = response.result()

    assert result["status"] == 204
    assert result["result"] == ""
