from gway import Gateway
from gway.remote.account import RemoteAccountApplication
from gway.remote.metadata import RemoteOAuthMetadata
from gway.remote.server import RemoteApplication
from gway.remote.session import RemoteSessionStore
from gway.sampler import load as load_sampler

AppSpec = load_sampler("web/app").AppSpec


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
        ("/remote.css", "GET", None),
        ("/remote.css", "HEAD", None),
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


def test_remote_apps_sharing_gateway_keep_request_state_isolated(tmp_path):
    runtime = Gateway(cache=tmp_path / "cache")
    metadata = RemoteOAuthMetadata.from_origin(
        "http://127.0.0.1:9000",
        allow_insecure_loopback=True,
    )
    first_account = RemoteAccountApplication(sessions=RemoteSessionStore())
    second_account = RemoteAccountApplication(sessions=RemoteSessionStore())
    first = RemoteApplication(metadata, runtime=runtime, account=first_account)
    second = RemoteApplication(metadata, runtime=runtime, account=second_account)

    first_status, first_headers, _ = first.response("GET", "/")
    second_status, second_headers, _ = second.response("GET", "/")

    assert first_status == second_status == 200
    first_id = first_headers["set-cookie"].split("=", 1)[1].split(";", 1)[0]
    second_id = second_headers["set-cookie"].split("=", 1)[1].split(";", 1)[0]
    assert first_account.sessions.get(first_id) is not None
    assert first_account.sessions.get(second_id) is None
    assert second_account.sessions.get(second_id) is not None
    assert second_account.sessions.get(first_id) is None


def test_remote_browser_dispatch_does_not_leak_gateway_result_history(tmp_path):
    runtime = Gateway(cache=tmp_path / "cache")
    metadata = RemoteOAuthMetadata.from_origin(
        "http://127.0.0.1:9000",
        allow_insecure_loopback=True,
    )
    application = RemoteApplication(metadata, runtime=runtime)
    initial_history = list(runtime.results.history)

    assert application.response("GET", "/privacy")[0] == 200
    assert application.response("GET", "/privacy")[0] == 200

    assert runtime.results.history == initial_history


def test_runtime_backed_browser_does_not_fall_back_to_legacy_routes(tmp_path):
    runtime = Gateway(cache=tmp_path / "cache")
    metadata = RemoteOAuthMetadata.from_origin(
        "http://127.0.0.1:9000",
        allow_insecure_loopback=True,
    )
    application = RemoteApplication(metadata, runtime=runtime)
    application.browser.app = AppSpec(
        name=application.browser.app.name,
        topic=application.browser.app.topic,
        route=application.browser.app.route,
        views=tuple(
            view
            for view in application.browser.app.views
            if view.resolved_route != "/login"
        ),
    )

    status, headers, payload = application.response("GET", "/login")

    assert status == 404
    assert headers == {}
    assert payload == {"error": "not_found"}


def test_remote_connect_uses_mobile_dark_recipe_template(tmp_path):
    runtime = Gateway(cache=tmp_path / "cache")
    metadata = RemoteOAuthMetadata.from_origin(
        "http://127.0.0.1:9000",
        allow_insecure_loopback=True,
    )
    application = RemoteApplication(metadata, runtime=runtime)

    status, headers, payload = application.response("GET", "/connect")

    assert status == 200
    assert headers["content-type"] == "text/html; charset=utf-8"
    assert 'name="viewport"' in payload
    assert 'content="width=device-width, initial-scale=1"' in payload
    assert 'type="password"' in payload
    assert 'autocapitalize="none"' in payload
    assert 'class="primary"' in payload
    assert 'href="/remote.css"' in payload

    css_status, css_headers, css = application.response("GET", "/remote.css")
    assert css_status == 200
    assert css_headers["content-type"] == "text/css"
    assert b"color-scheme: dark" in css
    assert b"min-height: 56px" in css\n    assert b"-webkit-text-size-adjust: 100%" in css\n    assert b"env(safe-area-inset-bottom)" in css\n    assert b"@media (max-width: 599px)" in css\n    assert b"overflow-wrap: anywhere" in css\n    assert b"min-height: 54px" in css


def test_templated_consent_redirect_is_preserved_without_rendering(tmp_path):
    runtime = Gateway(cache=tmp_path / "cache")
    metadata = RemoteOAuthMetadata.from_origin(
        "http://127.0.0.1:9000",
        allow_insecure_loopback=True,
    )
    application = RemoteApplication(metadata, runtime=runtime)

    status, headers, payload = application.response(
        "GET",
        "/consent?client_id=client&scope=full-access",
    )

    assert status == 303
    assert headers["location"] == "/connect"
    assert payload == ""


def test_remote_css_is_declared_for_public_https_proxy():
    from pathlib import Path

    template = Path("sampler/web/remote/nginx-https-[site].conf").read_text(
        encoding="utf-8"
    )

    assert "location = /remote.css {" in template
    assert "proxy_pass http://[auth_host|127.0.0.1]:[auth_port|8001];" in template



def test_remote_result_page_reuses_mobile_dark_shell():
    from gway.remote.browser import _result_page

    html = _result_page(
        "Access approved",
        "Return to the client.",
        action_href="/settings/connections",
        action_label="Manage connections",
    )

    assert 'name="viewport"' in html
    assert 'content="width=device-width, initial-scale=1"' in html
    assert 'href="/remote.css"' in html
    assert 'class="brand"' in html
    assert 'class="card"' in html
    assert 'class="button secondary"' in html
    assert "Access approved" in html
