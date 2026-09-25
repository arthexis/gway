import pytest

from gway.appexposure import ExposureSpec, LocalAppService
from gway.appspec import AppSpec


def test_expose_app_requires_known_local_target(gateway):
    gateway("setup app remote")

    with pytest.raises(ValueError, match="known local service"):
        gateway("expose app remote.example.com")


def test_expose_app_no_mutate_returns_inspectable_spec(gateway):
    app = gateway("setup app remote")

    exposure = gateway.execute(
        "expose app remote.example.com --host 127.0.0.1 --port 8001",
        mutate=False,
    )

    assert exposure == ExposureSpec(
        service=LocalAppService(
            app=app.name,
            host="127.0.0.1",
            port=8001,
        ),
        domain="remote.example.com",
    )


def test_expose_app_applies_existing_web_exposure_sampler(gateway, monkeypatch):
    calls = []

    def fake_run(runtime, recipe_name, **context):
        calls.append((runtime, recipe_name, context))
        return "applied"

    monkeypatch.setattr("gway.sampler.run", fake_run)
    gateway("setup app remote")

    exposure = gateway(
        "expose app remote.example.com "
        "--host 127.0.0.1 --port 8001 "
        "--email admin@example.com"
    )

    assert exposure.domain == "remote.example.com"
    assert calls == [
        (
            gateway,
            "web/expose/expose",
            {
                "site": "remote-example-com",
                "domain": "remote.example.com",
                "host": "127.0.0.1",
                "port": 8001,
                "email": "admin@example.com",
            },
        )
    ]


def test_expose_app_repeated_identical_apply_is_idempotent(gateway, monkeypatch):
    calls = []

    def fake_run(runtime, recipe_name, **context):
        calls.append(context)

    monkeypatch.setattr("gway.sampler.run", fake_run)
    gateway("setup app remote")
    command = (
        "expose app remote.example.com "
        "--host 127.0.0.1 --port 8001 "
        "--email admin@example.com"
    )

    first = gateway(command)
    second = gateway(command)

    assert second == first
    assert len(calls) == 1


def test_expose_app_rejects_conflicting_target(gateway, monkeypatch):
    monkeypatch.setattr("gway.sampler.run", lambda *args, **kwargs: None)
    gateway("setup app remote")
    gateway(
        "expose app remote.example.com "
        "--host 127.0.0.1 --port 8001 "
        "--email admin@example.com"
    )

    with pytest.raises(ValueError, match="conflicting exposure"):
        gateway(
            "expose app remote.example.com "
            "--host 127.0.0.1 --port 9000 "
            "--email admin@example.com"
        )


def test_exposure_identity_does_not_depend_on_app_topology(gateway):
    first = AppSpec(name="remote")
    second = AppSpec(name="remote", route="/api")
    service = LocalAppService(app="remote", host="127.0.0.1", port=8001)

    left = ExposureSpec(service=service, domain="remote.example.com")
    right = ExposureSpec(service=service, domain="remote.example.com")

    assert first != second
    assert left == right


def test_expose_app_accepts_explicit_service_descriptor(gateway):
    app = gateway("setup app remote")
    service = LocalAppService(
        app=app.name,
        host="127.0.0.1",
        port=8001,
    )

    exposure = gateway.expose_app(
        "remote.example.com",
        app=app,
        service=service,
        mutate=False,
    )

    assert exposure.service is service


def test_expose_app_rejects_service_and_host_port_together(gateway):
    app = gateway("setup app remote")
    service = LocalAppService(app="remote", host="127.0.0.1", port=8001)

    with pytest.raises(ValueError, match="either --service or --host/--port"):
        gateway.expose_app(
            "remote.example.com",
            app=app,
            service=service,
            host="127.0.0.1",
            port=8001,
            mutate=False,
        )


def test_apply_exposure_requires_tls_email(gateway):
    gateway("setup app remote")

    with pytest.raises(ValueError, match="requires --email"):
        gateway(
            "expose app remote.example.com "
            "--host 127.0.0.1 --port 8001"
        )


def test_concrete_exposure_adapter_rejects_non_root_route(gateway):
    gateway("setup app remote")

    with pytest.raises(NotImplementedError, match="only route /"):
        gateway(
            "expose app remote.example.com "
            "--host 127.0.0.1 --port 8001 "
            "--route /remote --email admin@example.com"
        )


def test_expose_app_is_mutating_but_supports_no_mutate(gateway):
    assert gateway.expose_app.mutates is True
    app = gateway("setup app remote")

    exposure = gateway.execute(
        "expose app remote.example.com --host 127.0.0.1 --port 8001",
        mutate=False,
    )

    assert exposure.service.app == app.name
