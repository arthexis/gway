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
    assert "<redacted>" in message
    assert "visible" in message


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
