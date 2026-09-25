import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from gway.appserver import ApplicationHTTPAdapter, build_app_server
from gway.appspec import AppSpec, ViewSpec


def _serve(server):
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread


def test_http_adapter_exposes_request_through_semantic_context(gateway):
    def inspect(request):
        return {
            "method": request.method,
            "path": request.split.path,
            "query": request.split.query,
        }

    gateway.wrap("demo.inspect", inspect)
    app = AppSpec(name="demo").add(
        ViewSpec("demo.inspect", route="/inspect")
    )
    application = ApplicationHTTPAdapter(gateway, app)
    initial_history = list(gateway.results.history)

    status, headers, payload = application.response(
        "GET",
        "/inspect?name=Ada",
    )

    assert status == 200
    assert headers == {}
    assert payload == {
        "method": "GET",
        "path": "/inspect",
        "query": "name=Ada",
    }
    assert gateway.results.history == initial_history


def test_http_adapter_preserves_explicit_handler_response(gateway):
    gateway.wrap(
        "demo.created",
        lambda: (
            201,
            {"location": "/items/42"},
            {"id": 42},
        ),
    )
    app = AppSpec(name="demo").add(
        ViewSpec("demo.created", route="/items", methods=("POST",))
    )
    application = ApplicationHTTPAdapter(gateway, app)

    assert application.response("POST", "/items") == (
        201,
        {"location": "/items/42"},
        {"id": 42},
    )


def test_http_adapter_reports_route_and_method_errors(gateway):
    gateway.wrap("demo.health", lambda: {"status": "ok"})
    app = AppSpec(name="demo").add(
        ViewSpec("demo.health", route="/health")
    )
    application = ApplicationHTTPAdapter(gateway, app)

    assert application.response("GET", "/missing") == (
        404,
        {},
        {"error": "not_found"},
    )
    assert application.response("POST", "/health") == (
        405,
        {"allow": "GET"},
        {"error": "method_not_allowed"},
    )


def test_appspec_can_be_served_over_real_http(gateway):
    def hello(request):
        return {
            "hello": request.headers.get("x-name", "world"),
            "method": request.method,
        }

    gateway.wrap("demo.hello", hello)
    app = AppSpec(name="demo").add(
        ViewSpec("demo.hello", route="/hello")
    )
    server = build_app_server(gateway, app, port=0)
    thread = _serve(server)
    host, port = server.server_address

    try:
        request = Request(
            f"http://{host}:{port}/hello",
            headers={"X-Name": "Ada"},
        )
        with urlopen(request, timeout=5) as response:
            assert response.status == 200
            assert response.headers["content-type"] == "application/json"
            assert json.loads(response.read()) == {
                "hello": "Ada",
                "method": "GET",
            }

        try:
            urlopen(
                Request(
                    f"http://{host}:{port}/hello",
                    data=b"",
                    method="POST",
                ),
                timeout=5,
            )
        except HTTPError as error:
            assert error.code == 405
            assert error.headers["allow"] == "GET"
            assert json.loads(error.read()) == {"error": "method_not_allowed"}
        else:
            raise AssertionError("POST /hello should be rejected")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
