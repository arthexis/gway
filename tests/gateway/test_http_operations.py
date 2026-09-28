import pytest

from gway.documentation import describe
from gway.mutation import mutates


def test_http_operations_have_conservative_mutation_contract(gateway):
    assert mutates(gateway.ops.resolve("http.get")) is False
    for name in ("http.post", "http.put", "http.patch", "http.delete", "http.request"):
        assert mutates(gateway.ops.resolve(name)) is True


def test_http_get_is_allowed_in_no_mutate_mode(gateway, monkeypatch):
    monkeypatch.setattr(
        "gway.httpops.controller.transport_request",
        lambda *_args, **_kwargs: type(
            "Response",
            (),
            {"result": lambda self: {"status": 200, "result": {"ready": True}}},
        )(),
    )

    result = gateway.execute("http get https://example.test/status", mutate=False)

    assert result["status"] == 200
    assert result["result"] == {"ready": True}


@pytest.mark.parametrize("operation", ["post", "put", "patch", "delete", "request"])
def test_mutating_http_operations_are_rejected_in_no_mutate_mode(gateway, operation):
    from gway.mutation import MutationError

    with pytest.raises(MutationError):
        gateway.execute(
            f"http {operation} https://example.test/resource",
            mutate=False,
        )


def test_http_get_accepts_json_query_mapping(gateway, monkeypatch):
    observed = {}

    def fake(method, url, **kwargs):
        observed.update({"method": method, "url": url, **kwargs})
        return type(
            "Response",
            (),
            {"result": lambda self: {"status": 200, "result": "ok"}},
        )()

    monkeypatch.setattr("gway.httpops.controller.transport_request", fake)

    gateway('http get https://example.test/items --params {"page":2}')

    assert observed["method"] == "GET"
    assert observed["params"] == {"page": 2}


def test_http_post_decodes_json_body(gateway, monkeypatch):
    observed = {}

    def fake(method, url, **kwargs):
        observed.update({"method": method, "url": url, **kwargs})
        return type(
            "Response",
            (),
            {"result": lambda self: {"status": 201, "result": "created"}},
        )()

    monkeypatch.setattr("gway.httpops.controller.transport_request", fake)

    result = gateway(
        'http post https://example.test/items --json {"name":"Ada"}'
    )

    assert result["status"] == 201
    assert observed["method"] == "POST"
    assert observed["json"] == {"name": "Ada"}


def test_http_operations_are_discoverable_with_documentation(gateway):
    operation = gateway.ops.resolve("http.get")
    documentation = describe(operation)

    assert documentation.path == ("http", "get")
    assert documentation.summary == "Perform a non-mutating HTTP GET request."
    assert documentation.parameter("url").required is True
    assert documentation.parameter("follow_redirects").default is False


def test_http_result_composes_through_gateway_chain(gateway, monkeypatch):
    monkeypatch.setattr(
        "gway.httpops.controller.transport_request",
        lambda *_args, **_kwargs: type(
            "Response",
            (),
            {
                "result": lambda self: {
                    "status": 200,
                    "url": "https://example.test/status",
                    "headers": {},
                    "result": {"ready": True},
                }
            },
        )(),
    )

    result = gateway("http get https://example.test/status ; check status --is 200")

    assert result is True
