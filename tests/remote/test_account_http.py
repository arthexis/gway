import http.client
import re
import threading
from urllib.parse import urlencode

from gway import Gateway
from gway.remote.account import RemoteAccountApplication
from gway.remote.server import build_server
from gway.remote.session import RemoteSessionStore
from gway.security.oauth import OAuthRegistry
from gway.security.scopes import ScopeRegistry
from gway.security.tokens import TokenRegistry


def _csrf(html):
    match = re.search(r'name="csrf" value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


def _cookie(value):
    return value.split(";", 1)[0]


def test_real_http_browser_link_consent_and_revoke_flow(tmp_path):
    path = tmp_path / "security.sqlite"
    scopes = ScopeRegistry(path)
    tokens = TokenRegistry(path)
    oauth = OAuthRegistry(path)
    scopes.replace(
        "chatgpt-logs",
        operations={"log.sources", "log.read", "log.tail", "log.search"},
        environment=(),
    )
    issued = tokens.create("operator", scopes={"chatgpt-logs"})
    account = RemoteAccountApplication(
        oauth=oauth,
        tokens=tokens,
        sessions=RemoteSessionStore(lifetime_seconds=300),
    )
    runtime = Gateway(cache=tmp_path / "gway-cache")
    server = build_server(
        "127.0.0.1",
        0,
        public_origin="http://127.0.0.1:9000",
        allow_insecure_loopback=True,
        account=account,
        runtime=runtime,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    connection = http.client.HTTPConnection(host, port, timeout=2)

    try:
        connection.request(
            "GET",
            "/consent?client_id=https%3A%2F%2Fchatgpt.com%2Fclient.json"
            "&scope=chatgpt-logs",
        )
        response = connection.getresponse()
        assert response.status == 303
        first_cookie = _cookie(response.getheader("Set-Cookie"))
        assert response.getheader("Location") == "/connect"
        response.read()

        connection.request("GET", "/connect", headers={"Cookie": first_cookie})
        response = connection.getresponse()
        assert response.status == 200
        connect_html = response.read().decode()
        connect_csrf = _csrf(connect_html)

        form = urlencode({"csrf": connect_csrf, "bearer": issued.bearer})
        connection.request(
            "POST",
            "/connect",
            body=form,
            headers={
                "Cookie": first_cookie,
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        response = connection.getresponse()
        assert response.status == 303
        assert response.getheader("Location") == "/consent"
        second_cookie = _cookie(response.getheader("Set-Cookie"))
        assert second_cookie != first_cookie
        response.read()

        connection.request("GET", "/consent", headers={"Cookie": second_cookie})
        response = connection.getresponse()
        assert response.status == 200
        consent_html = response.read().decode()
        assert "chatgpt-logs" in consent_html
        assert "log.sources" in consent_html
        assert "log.read" in consent_html
        assert "log.tail" in consent_html
        assert "log.search" in consent_html
        consent_csrf = _csrf(consent_html)

        form = urlencode({"csrf": consent_csrf, "decision": "approve"})
        connection.request(
            "POST",
            "/consent",
            body=form,
            headers={
                "Cookie": second_cookie,
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        response = connection.getresponse()
        assert response.status == 200
        assert "Access approved" in response.read().decode()

        session_id = second_cookie.split("=", 1)[1]
        session = account.sessions.require(session_id)
        assert session.approved_grant_id is not None
        grant = oauth.get_grant(session.approved_grant_id)
        assert grant.scopes == frozenset({"chatgpt-logs"})

        connection.request(
            "GET",
            "/settings/connections",
            headers={"Cookie": second_cookie},
        )
        response = connection.getresponse()
        settings_html = response.read().decode()
        assert response.status == 200
        assert "connected" in settings_html
        settings_csrf = _csrf(settings_html)

        form = urlencode({"csrf": settings_csrf, "action": "revoke"})
        connection.request(
            "POST",
            "/settings/connections",
            body=form,
            headers={
                "Cookie": second_cookie,
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        response = connection.getresponse()
        assert response.status == 303
        assert response.getheader("Location") == "/settings/connections"
        response.read()

        assert oauth.get_link(grant.link_name).revoked_at is not None
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_secure_public_origin_marks_browser_cookie_secure(tmp_path):
    path = tmp_path / "security.sqlite"
    account = RemoteAccountApplication(
        oauth=OAuthRegistry(path),
        tokens=TokenRegistry(path),
        sessions=RemoteSessionStore(),
    )
    server = build_server(
        "127.0.0.1",
        0,
        public_origin="https://remote.example.test",
        account=account,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    connection = http.client.HTTPConnection(host, port, timeout=2)

    try:
        connection.request("GET", "/connect")
        response = connection.getresponse()
        cookie = response.getheader("Set-Cookie")
        response.read()

        assert response.status == 200
        assert "HttpOnly" in cookie
        assert "SameSite=Lax" in cookie
        assert "Secure" in cookie
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_real_http_consent_is_informational_and_grants_full_bearer_scope_set(tmp_path):
    path = tmp_path / "security.sqlite"
    scopes = ScopeRegistry(path)
    tokens = TokenRegistry(path)
    oauth = OAuthRegistry(path)
    scopes.replace("read", operations={"log.read"}, environment=())
    scopes.replace("write", operations={"service.restart"}, environment=())
    issued = tokens.create("operator", scopes={"read", "write"})
    account = RemoteAccountApplication(
        oauth=oauth,
        tokens=tokens,
        sessions=RemoteSessionStore(lifetime_seconds=300),
    )
    server = build_server(
        "127.0.0.1",
        0,
        public_origin="http://127.0.0.1:9000",
        allow_insecure_loopback=True,
        account=account,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    connection = http.client.HTTPConnection(host, port, timeout=2)

    try:
        connection.request(
            "GET",
            "/consent?client_id=client&scope=read",
        )
        response = connection.getresponse()
        first_cookie = _cookie(response.getheader("Set-Cookie"))
        response.read()

        connection.request("GET", "/connect", headers={"Cookie": first_cookie})
        response = connection.getresponse()
        connect_csrf = _csrf(response.read().decode())

        connection.request(
            "POST",
            "/connect",
            body=urlencode({"csrf": connect_csrf, "bearer": issued.bearer}),
            headers={
                "Cookie": first_cookie,
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        response = connection.getresponse()
        second_cookie = _cookie(response.getheader("Set-Cookie"))
        response.read()

        connection.request("GET", "/consent", headers={"Cookie": second_cookie})
        response = connection.getresponse()
        html = response.read().decode()
        consent_csrf = _csrf(html)
        assert "<strong>read</strong>" in html
        assert "<strong>write</strong>" in html
        assert 'name="scope"' not in html
        assert "informational" in html
        assert "1 operations" in html

        connection.request(
            "POST",
            "/consent",
            body=urlencode({"csrf": consent_csrf, "decision": "approve"}),
            headers={
                "Cookie": second_cookie,
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        response = connection.getresponse()
        assert response.status == 200
        response.read()

        session = account.sessions.require(second_cookie.split("=", 1)[1])
        grant = oauth.get_grant(session.approved_grant_id)
        assert grant.scopes == frozenset({"read", "write"})
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

def test_consent_renders_preview_and_expandable_full_operations_per_scope(tmp_path):
    path = tmp_path / "security.sqlite"
    scopes = ScopeRegistry(path)
    tokens = TokenRegistry(path)
    oauth = OAuthRegistry(path)
    scopes.replace(
        "alpha",
        operations={f"alpha.{index}" for index in range(8)},
        environment=(),
    )
    scopes.replace(
        "beta",
        operations={f"beta.{index}" for index in range(8)},
        environment=(),
    )
    issued = tokens.create("operator", scopes={"alpha", "beta"})
    account = RemoteAccountApplication(
        oauth=oauth,
        tokens=tokens,
        sessions=RemoteSessionStore(lifetime_seconds=300),
    )
    session = account.new_session()
    account.connect(session, csrf=session.csrf, bearer=issued.bearer)
    account.stage_consent(session, "client", {"alpha", "beta"})

    html = account.consent_page(session)

    assert "alpha.0" in html
    assert "beta.0" in html
    assert html.count("…and 2 more") >= 2
    assert html.count("See all 8 operations") >= 2
    assert "alpha.7" in html
    assert "beta.7" in html
