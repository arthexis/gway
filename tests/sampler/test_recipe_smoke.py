from gway import Gateway


def test_dns_http_recipe_retries_boolean_readiness_in_same_pipeline(monkeypatch, run_recipe):
    from gway.dns import Controller as DNSController

    attempts = []

    monkeypatch.setattr(
        DNSController,
        "create",
        lambda self, domain, **kwargs: {"domain": domain, **kwargs},
    )

    def ready(self, domain, **kwargs):
        attempts.append((domain, kwargs))
        return len(attempts) >= 3

    monkeypatch.setattr(DNSController, "ready", ready)
    monkeypatch.setattr("gway.dispatch.time.sleep", lambda _seconds: None)

    runtime = Gateway()
    result = run_recipe(
        runtime,
        "web/expose/dns-http.rx",
        domain="register.arthexis.com",
        public_ipv4="192.0.2.10",
        zone="arthexis.com",
    )

    assert result is True
    assert len(attempts) == 3


def test_wire_watchtower_recipe_smoke_executes_with_fake_host_adapters(monkeypatch, run_recipe):
    from gway.filesystem import Filesystem
    from gway.gateway import Gateway as GatewayClass
    from gway.rendering import Renderer
    from gway.service.controller import Controller as ServiceController
    from gway.sampler import load

    wire = load("wire")
    calls = []

    def fake_ingest(self, source, *, kind=None, sudo=False, **kwargs):
        calls.append(("ingest", str(source), kind, sudo))
        if kind == "proc" and self.ops.resolve(str(source)) is None:
            def invoke_proc(*args, **options):
                calls.append(("proc", str(source), tuple(args), options))
                return {
                    "command": str(source),
                    "args": list(args),
                    "options": options,
                }

            operation = self.wrap(str(source), invoke_proc)
            setattr(self, f"_smoke_{str(source).replace('-', '_')}", operation)
        return str(source)

    monkeypatch.setattr(GatewayClass, "ingest", fake_ingest)
    monkeypatch.setattr(
        GatewayClass,
        "_commit_journal",
        lambda self, name: calls.append(("commit", name)) or name,
    )
    monkeypatch.setattr(
        Renderer,
        "render",
        lambda self, template, to, **kwargs: calls.append(
            ("render", str(template), str(to))
        )
        or str(to),
    )
    monkeypatch.setattr(
        Filesystem,
        "link",
        lambda self, source, to, **kwargs: calls.append(
            ("link", str(source), str(to))
        )
        or str(to),
    )
    monkeypatch.setattr(
        ServiceController,
        "install",
        lambda self, *target, **kwargs: calls.append(
            ("service.install", target, kwargs)
        )
        or {"installed": True},
    )
    monkeypatch.setattr(
        ServiceController,
        "start",
        lambda self, *target, **kwargs: calls.append(
            ("service.start", target, kwargs)
        )
        or {"active": True},
    )
    monkeypatch.setattr(
        wire.Controller,
        "deploy_server",
        lambda self, **kwargs: calls.append(("wire.deploy", kwargs))
        or {"ready": True},
    )
    monkeypatch.setattr(
        wire.Controller,
        "activate",
        lambda self, interface="gway", **kwargs: calls.append(
            ("wire.activate", interface, kwargs)
        )
        or {"active": True},
    )
    monkeypatch.setattr(
        wire.Controller,
        "server_check",
        lambda self, **kwargs: calls.append(("wire.check", kwargs))
        or {"ready": True},
    )

    runtime = Gateway()
    result = run_recipe(
        runtime,
        "wire/watchtower.rx",
        email="ops@example.com",
        public_address="192.0.2.10",
    )

    assert result == {"ready": True}
    names = [call[0] for call in calls]
    assert "wire.deploy" in names
    assert "wire.activate" in names
    assert "commit" in names
    assert "service.install" in names
    assert "service.start" in names
    assert "render" in names
    assert "wire.check" in names

    certbot_calls = [
        call for call in calls
        if call[0] == "proc" and call[1] == "certbot"
    ]
    assert len(certbot_calls) == 1
    certbot_args = certbot_calls[0][2]
    certbot_options = certbot_calls[0][3]
    assert certbot_args == ("certonly",)
    assert certbot_options["domain"] == "register.arthexis.com"
    assert certbot_options["cert_name"] == "register.arthexis.com"
    assert certbot_options["email"] == "ops@example.com"
    assert "[domain]" not in certbot_options.values()
    assert "[email]" not in certbot_options.values()


def test_mcp_server_recipe_smoke_executes_with_fake_server(monkeypatch, run_recipe):
    observed = {}

    monkeypatch.setattr(
        "gway.recipe.runtime.prepare_required_companion",
        lambda runtime, frame: None,
    )
    monkeypatch.setattr(
        "gway.recipe.runtime.ingest_companion",
        lambda runtime, recipe_filename: [],
    )

    runtime = Gateway()

    def serve(
        host="127.0.0.1",
        port: int = 8000,
        route="/mcp",
        endpoint=None,
    ):
        observed.update(
            host=host,
            port=port,
            route=route,
            endpoint=endpoint,
        )
        return {"served": True}

    runtime.server_serve = runtime.wrap("server.serve", serve)

    result = run_recipe(runtime, "mcp/server.rx")

    assert result == {"served": True}
    assert observed == {
        "host": "127.0.0.1",
        "port": 8000,
        "route": "/mcp",
        "endpoint": "http://127.0.0.1:8000/mcp",
    }
