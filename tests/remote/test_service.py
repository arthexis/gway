import http.client
import socket
import time


from gway import Gateway
from gway.install.service import ServiceInstallState
from gway.install.service import systemd
from gway.security.oauth import OAuthRegistry
from gway.security.scopes import ScopeRegistry
from gway.security.tokens import TokenRegistry


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def _target(port):
    return (
        "remote serve 127.0.0.1 "
        f"{port} --public-origin https://remote.example.test "
        "--resource-path /mcp"
    )


def _wait_http(port, path="/.well-known/oauth-authorization-server"):
    deadline = time.monotonic() + 10
    last_error = None
    while time.monotonic() < deadline:
        try:
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
            connection.request("GET", path)
            response = connection.getresponse()
            payload = response.read()
            connection.close()
            return response.status, payload
        except OSError as error:
            last_error = error
            time.sleep(0.05)
    raise AssertionError(f"remote-auth service did not become ready: {last_error}")


def test_remote_auth_is_builtin_service_preset():
    gateway = Gateway()

    definition = gateway._service_controller._definition(("remote", "serve"))

    assert definition.identity == ("gway", "remote-auth")
    assert definition.description == "Gway remote OAuth and account service"
    assert definition.launchable.kind == "operation"
    assert definition.launchable.name == "remote.serve"
    assert definition.launchable.command == (
        "{python}",
        "-m",
        "gway",
        "remote",
        "serve",
    )


def test_remote_auth_systemd_rendering_uses_generic_backend():
    gateway = Gateway()
    definition = gateway._service_controller._definition(("remote", "serve"))

    rendered = systemd.render(definition)

    assert "Description=Gway remote OAuth and account service" in rendered
    assert "ExecStart=" in rendered
    assert " remote serve" in rendered
    assert "Restart=no" in rendered
    assert "gway.service.supervisor" in rendered
    assert "systemctl" not in rendered
    assert "daemon-reload" not in rendered


def test_remote_auth_process_service_start_status_restart_stop(tmp_path, monkeypatch):
    data_root = tmp_path / "data"
    cache_root = tmp_path / "cache"
    monkeypatch.setenv("GWAY_DATA_DIR", str(data_root))
    monkeypatch.setenv("GWAY_CACHE_DIR", str(cache_root))

    gateway = Gateway()
    port = _free_port()
    target = _target(port)

    records = gateway._service_controller.install(
        *target.split(),
        backend="process",
        restart="no",
    )
    assert records[0].service == "remote-auth"
    assert records[0].backend == "process"

    started = gateway._service_controller.start(*target.split())
    first_pid = started["pid"]

    try:
        assert started["running"] is True
        assert started["service"] == "remote-auth"
        status_code, payload = _wait_http(port)
        assert status_code == 200
        assert b'"issuer":"https://remote.example.test"' in payload

        status = gateway._service_controller.status(*target.split())
        assert status["running"] is True
        assert status["pid"] == first_pid

        restarted = gateway._service_controller.restart(*target.split())
        assert restarted["running"] is True
        assert restarted["pid"] is not None
        assert restarted["pid"] != first_pid

        status_code, payload = _wait_http(port)
        assert status_code == 200
        assert b'"token_endpoint":"https://remote.example.test/oauth/token"' in payload
    finally:
        stopped = gateway._service_controller.stop(*target.split())

    assert stopped["running"] is False
    assert stopped["pid"] is None


def test_remote_security_state_survives_service_reinstall_and_fresh_gateway(
    tmp_path,
    monkeypatch,
):
    data_root = tmp_path / "data"
    cache_root = tmp_path / "durable-cache"
    monkeypatch.setenv("GWAY_DATA_DIR", str(data_root))
    monkeypatch.setenv("GWAY_CACHE_DIR", str(cache_root))

    first = Gateway()
    scopes = ScopeRegistry(first.security_path)
    tokens = TokenRegistry(first.security_path)
    oauth = OAuthRegistry(first.security_path)
    scopes.replace("chatgpt-logs", operations={"log.read"})
    tokens.create("operator", scopes={"chatgpt-logs"})
    oauth.link("chatgpt", "operator")
    grant = oauth.create_grant(
        "chatgpt",
        "chatgpt-client",
        scopes={"chatgpt-logs"},
        resource="https://remote.example.test/mcp",
    )
    issued = oauth.issue_tokens(grant.id)

    first._service_controller.install(
        "remote",
        "serve",
        backend="process",
        restart="no",
    )
    first._service_controller.install(
        "remote",
        "serve",
        backend="process",
        restart="no",
    )

    assert (cache_root / "security" / "state.sqlite").is_file()

    fresh = Gateway()
    definition = fresh._service_controller._definition(("remote", "serve"))
    assert definition.identity == ("gway", "remote-auth")

    authenticated = OAuthRegistry(fresh.security_path).authenticate_access(
        issued.access_token
    )
    assert authenticated.grant.id == grant.id
    assert authenticated.authority.operations == frozenset({"log.read"})

    records = ServiceInstallState(data_root / "services-installed").get("gway")
    remote_records = [item for item in records if item.service == "remote-auth"]
    assert len(remote_records) == 1
