from pathlib import Path

import pytest

from gway.appserver import ApplicationHTTPAdapter


def test_false_policy_returns_403_before_handler(gateway):
    calls = []

    def session(request):
        assert request.path == "/private"
        return False

    def private():
        calls.append("handler")
        return {"ok": True}

    gateway.wrap("site.session", session)
    gateway.wrap("site.private", private)
    gateway("setup app --topic site")
    app = gateway("view private --route /private --auth session")
    application = ApplicationHTTPAdapter(gateway, app)

    assert application.response("GET", "/private") == (
        403,
        {},
        {"error": "forbidden"},
    )
    assert calls == []


def test_policy_may_short_circuit_with_explicit_response(gateway):
    gateway.wrap(
        "site.session",
        lambda request: (
            302,
            {"location": "/login"},
            "",
        ),
    )
    gateway.wrap("site.private", lambda: {"ok": True})
    gateway("setup app --topic site")
    app = gateway("view private --route /private --auth session")

    assert ApplicationHTTPAdapter(gateway, app).response(
        "GET",
        "/private",
    ) == (
        302,
        {"location": "/login"},
        "",
    )


def test_public_policy_allows_without_resolving_operation(gateway):
    gateway.wrap("site.home", lambda: {"ok": True})
    gateway("setup app --topic site")
    app = gateway("view home --route / --auth public")

    assert ApplicationHTTPAdapter(gateway, app).response("GET", "/") == (
        200,
        {},
        {"ok": True},
    )


def test_invalid_policy_contract_returns_500(gateway):
    gateway.wrap("site.session", lambda: "maybe")
    gateway.wrap("site.private", lambda: {"ok": True})
    gateway("setup app --topic site")
    app = gateway("view private --route /private --auth session")

    status, _, payload = ApplicationHTTPAdapter(gateway, app).response(
        "GET",
        "/private",
    )

    assert status == 500
    assert payload["error"] == "invalid_policy"


def test_app_default_template_resolves_filename_and_body_sigils(
    gateway,
    tmp_path,
):
    templates = tmp_path / "templates"
    templates.mkdir()
    (templates / "dashboard.html").write_text(
        "<h1>[title]</h1>"
        "<p>[view] [route] [method]</p>",
        encoding="utf-8",
    )

    gateway.wrap(
        "site.dashboard",
        lambda: {"title": "Healthy"},
    )
    app = gateway(
        f"setup app --topic site --templates {templates} "
        '--template "[view].html"'
    )
    app = gateway("view dashboard --route /dashboard")
    application = ApplicationHTTPAdapter(gateway, app)

    assert application.response("GET", "/dashboard") == (
        200,
        {"content-type": "text/html; charset=utf-8"},
        "<h1>Healthy</h1><p>dashboard /dashboard GET</p>",
    )


def test_view_template_override_uses_recipe_directory_as_base(
    gateway,
    tmp_path,
):
    recipe = tmp_path / "site.rx"
    template = tmp_path / "special.html"
    template.write_text(
        "[message] from [view]",
        encoding="utf-8",
    )
    companion = tmp_path / "site.py"
    companion.write_text(
        "def dashboard():\n"
        "    return {'message': 'hello'}\n",
        encoding="utf-8",
    )
    recipe.write_text(
        "setup app --topic site\n"
        "view dashboard --route /dashboard --template special.html\n",
        encoding="utf-8",
    )

    app = gateway(recipe)

    assert Path(app.templates) == tmp_path.resolve()
    assert ApplicationHTTPAdapter(gateway, app).response(
        "GET",
        "/dashboard",
    ) == (
        200,
        {"content-type": "text/html; charset=utf-8"},
        "hello from dashboard",
    )


def test_template_renders_after_response_validation(gateway, tmp_path):
    from pydantic import BaseModel

    class ViewModel(BaseModel):
        count: int

    gateway.context["ViewModel"] = ViewModel
    template = tmp_path / "count.html"
    template.write_text("count=[count]", encoding="utf-8")
    gateway.wrap("site.count", lambda: {"count": "4"})
    app = gateway(
        f"setup app --topic site --templates {tmp_path}"
    )
    app = gateway(
        "view count --route /count "
        "--response-model ViewModel --template count.html"
    )

    assert ApplicationHTTPAdapter(gateway, app).response(
        "GET",
        "/count",
    ) == (
        200,
        {"content-type": "text/html; charset=utf-8"},
        "count=4",
    )


def test_template_can_use_request_sigil(gateway, tmp_path):
    template = tmp_path / "request.html"
    template.write_text("[request.path]", encoding="utf-8")
    gateway.wrap("site.where", lambda: {})
    app = gateway(
        f"setup app --topic site --templates {tmp_path}"
    )
    app = gateway(
        "view where --route /where --template request.html"
    )

    assert ApplicationHTTPAdapter(gateway, app).response(
        "GET",
        "/where",
    ) == (
        200,
        {"content-type": "text/html; charset=utf-8"},
        "/where",
    )


def test_missing_template_returns_500(gateway, tmp_path):
    gateway.wrap("site.home", lambda: {"name": "home"})
    app = gateway(
        f"setup app --topic site --templates {tmp_path}"
    )
    app = gateway("view home --template missing.html")

    status, _, payload = ApplicationHTTPAdapter(gateway, app).response(
        "GET",
        "/home",
    )

    assert status == 500
    assert payload["error"] == "template_error"


def test_static_view_rejects_auth_and_template(gateway, tmp_path):
    source = tmp_path / "index.html"
    source.write_text("static", encoding="utf-8")
    gateway("setup app site")

    with pytest.raises(ValueError, match="do not support auth or templates"):
        gateway(
            f"view --route /index --static {source} --auth public"
        )
