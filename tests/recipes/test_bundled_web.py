from gway.bundled import resolve, run
from gway.gateway import Gateway


def test_bundled_web_exposure_resolves_default_and_children():
    default = resolve("web/expose")
    http = resolve("web/expose/http")
    https = resolve("web/expose/https")

    assert default.name == "expose.rx"
    assert http.name == "http.rx"
    assert https.name == "https.rx"
    assert default.parent == http.parent == https.parent


def test_bundled_web_recipe_is_available_through_gateway(monkeypatch):
    runtime = Gateway()
    observed = {}

    def fake_run(runtime_arg, recipe_name, **context):
        observed.update(name=recipe_name, context=context)
        assert runtime_arg is runtime
        return "ok"

    monkeypatch.setattr("gway.bundled.run", fake_run)

    assert (
        runtime(
            "recipe web/expose --name arthexis --domain arthexis.com "
            "--host 127.0.0.1 --port 8888 --email ops@example.com"
        )
        == "ok"
    )
    assert observed["name"] == "web/expose"
    assert observed["context"]["domain"] == "arthexis.com"
    assert observed["context"]["port"] == "8888"


def test_bundled_run_accepts_name_in_recipe_context(monkeypatch):
    runtime = Gateway(context={"name": "old"})
    observed = {}

    def fake_execute(runtime_arg, path, *, context):
        runtime_arg.context.update(context)
        observed.update(runtime=runtime_arg, path=path, context=context)
        return {}, "ok"

    monkeypatch.setattr("gway.bundled.execute_recipe", fake_execute)

    assert run(runtime, "web/expose", name="arthexis") == "ok"
    assert observed["runtime"] is runtime
    assert observed["path"] == resolve("web/expose")
    assert observed["context"]["name"] == "arthexis"
    assert runtime.context["name"] == "arthexis"


def test_web_exposure_recipe_keeps_dns_out_of_default_flow():
    root = resolve("web/expose").parent
    default = (root / "expose.rx").read_text(encoding="utf-8")
    http = (root / "http.rx").read_text(encoding="utf-8")
    https = (root / "https.rx").read_text(encoding="utf-8")

    combined = "\n".join((default, http, https)).casefold()
    assert "dns create" not in combined
    assert "dns delete" not in combined
    assert "certbot certonly" in combined
    assert "nginx -t" in combined


def test_web_templates_proxy_requested_loopback_context():
    root = resolve("web/expose").parent
    http = (root / "nginx-http-[name].conf").read_text(encoding="utf-8")
    https = (root / "nginx-https-[name].conf").read_text(encoding="utf-8")

    assert "proxy_pass http://[host]:[port];" in http
    assert "proxy_pass http://[host]:[port];" in https
    assert "/etc/letsencrypt/live/[domain]/fullchain.pem" in https
