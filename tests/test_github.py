import httpx
import pytest

from gway.github import Client, GitHubError


def transport(handler):
    return httpx.MockTransport(handler)


def test_client_sends_github_headers_without_exposing_token():
    observed = {}

    def handler(request):
        observed["authorization"] = request.headers["authorization"]
        observed["version"] = request.headers["x-github-api-version"]
        return httpx.Response(200, json={"id": 1}, request=request)

    client = Client("secret-token", transport=transport(handler))
    response = client.request("GET", "/user")

    assert observed["authorization"] == "Bearer secret-token"
    assert observed["version"] == "2022-11-28"
    assert response.data == {"id": 1}
    assert "secret-token" not in repr(response)


def test_client_accepts_github_app_installation_token():
    client = Client(
        "ghs_installation_token",
        transport=transport(
            lambda request: httpx.Response(
                200,
                json={"authorization": request.headers["authorization"]},
                request=request,
            )
        ),
    )

    assert client.request("GET", "/installation/repositories").data == {
        "authorization": "Bearer ghs_installation_token"
    }


def test_client_normalizes_error_without_credentials():
    client = Client(
        "secret-token",
        transport=transport(
            lambda request: httpx.Response(
                403,
                json={"message": "Resource not accessible"},
                headers={"X-GitHub-Request-Id": "ABC:123"},
                request=request,
            )
        ),
    )

    with pytest.raises(GitHubError) as captured:
        client.request("GET", "/repos/example/private")

    error = captured.value
    assert error.status == 403
    assert error.request_id == "ABC:123"
    assert "Resource not accessible" in str(error)
    assert "secret-token" not in str(error)


def test_client_exposes_rate_limit_metadata():
    client = Client(
        "token",
        transport=transport(
            lambda request: httpx.Response(
                200,
                json=[],
                headers={
                    "X-RateLimit-Limit": "5000",
                    "X-RateLimit-Remaining": "4999",
                    "X-RateLimit-Reset": "1700000000",
                    "X-RateLimit-Resource": "core",
                },
                request=request,
            )
        ),
    )

    rate = client.request("GET", "/repos/example/repo/issues").rate_limit

    assert rate.limit == 5000
    assert rate.remaining == 4999
    assert rate.reset == 1700000000
    assert rate.resource == "core"


def test_pages_follows_only_github_link_next():
    seen = []

    def handler(request):
        seen.append(str(request.url))
        if request.url.params.get("page") == "2":
            return httpx.Response(200, json=[2], request=request)
        return httpx.Response(
            200,
            json=[1],
            headers={
                "Link": (
                    '<https://api.github.com/items?page=2>; rel="next", '
                    '<https://api.github.com/items?page=2>; rel="last"'
                )
            },
            request=request,
        )

    pages = list(Client("token", transport=transport(handler)).pages("/items"))

    assert [page.data for page in pages] == [[1], [2]]
    assert seen == [
        "https://api.github.com/items",
        "https://api.github.com/items?page=2",
    ]


def test_client_does_not_follow_redirects_with_credentials():
    client = Client(
        "secret-token",
        transport=transport(
            lambda request: httpx.Response(
                302,
                headers={"Location": "https://attacker.example/steal"},
                request=request,
            )
        ),
    )

    response = client.request("GET", "/repos/example/repo")

    assert response.status == 302


def test_client_rejects_cross_origin_absolute_requests():
    client = Client("secret-token", transport=transport(lambda request: None))

    with pytest.raises(ValueError, match="configured API origin"):
        client.request("GET", "https://attacker.example/items?page=2")


def test_custom_headers_cannot_replace_authorization():
    observed = {}

    def handler(request):
        observed["authorization"] = request.headers["authorization"]
        return httpx.Response(200, json={}, request=request)

    client = Client("secret-token", transport=transport(handler))
    client.request(
        "GET",
        "/user",
        headers={"Authorization": "Bearer attacker-controlled"},
    )

    assert observed["authorization"] == "Bearer secret-token"


def test_pages_rejects_cross_origin_link_next():
    def handler(request):
        return httpx.Response(
            200,
            json=[1],
            headers={
                "Link": '<https://attacker.example/items?page=2>; rel="next"'
            },
            request=request,
        )

    client = Client("secret-token", transport=transport(handler))

    with pytest.raises(ValueError, match="configured API origin"):
        list(client.pages("/items"))
