from gway import Gateway
from gway.remote.metadata import RemoteOAuthMetadata
from gway.remote.server import RemoteApplication


def test_remote_browser_topology_is_recipe_composed(tmp_path):
    runtime = Gateway(cache=tmp_path / "cache")
    metadata = RemoteOAuthMetadata.from_origin(
        "http://127.0.0.1:9000",
        allow_insecure_loopback=True,
    )

    application = RemoteApplication(metadata, runtime=runtime)

    assert [
        (route.route, route.method, route.handler)
        for route in application.browser.app.routes
    ] == [
        ("/", "GET", "remote.browser.index"),
        ("/login", "GET", "remote.browser.login"),
        ("/privacy", "GET", "remote.browser.privacy"),
        ("/connect", "GET", "remote.browser.connect"),
        ("/connect", "POST", "remote.browser.connect"),
        ("/consent", "GET", "remote.browser.consent"),
        ("/consent", "POST", "remote.browser.consent"),
        ("/settings/connections", "GET", "remote.browser.connections"),
        ("/settings/connections", "POST", "remote.browser.connections"),
    ]


def test_remote_browser_recipe_controls_method_contract(tmp_path):
    runtime = Gateway(cache=tmp_path / "cache")
    metadata = RemoteOAuthMetadata.from_origin(
        "http://127.0.0.1:9000",
        allow_insecure_loopback=True,
    )
    application = RemoteApplication(metadata, runtime=runtime)

    status, headers, payload = application.response("DELETE", "/connect")

    assert status == 405
    assert headers == {"allow": "GET, POST"}
    assert payload == {"error": "method_not_allowed"}
