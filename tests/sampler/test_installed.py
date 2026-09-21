from gway.gateway import Gateway
from gway.sampler import resolve, run


def test_sampler_recipe_resolves_default_and_children():
    default = resolve("web/expose")
    http = resolve("web/expose/http")
    https = resolve("web/expose/https")

    assert default.name == "expose.rx"
    assert http.name == "http.rx"
    assert https.name == "https.rx"
    assert default.parent == http.parent == https.parent
    assert "sampler" in default.parts


def test_sampler_recipe_is_available_through_gateway(monkeypatch):
    runtime = Gateway()
    observed = {}

    def fake_run(runtime_arg, recipe_name, **context):
        observed.update(recipe_name=recipe_name, context=context)
        assert runtime_arg is runtime
        return "ok"

    monkeypatch.setattr("gway.sampler.run", fake_run)

    assert (
        runtime(
            "recipe web/expose --site arthexis.com --domain arthexis.com "
            "--host 127.0.0.1 --port 8888 --email ops@example.com"
        )
        == "ok"
    )
    assert observed["recipe_name"] == "web/expose"
    assert observed["context"]["site"] == "arthexis.com"


def test_sampler_run_preserves_explicit_name_context(monkeypatch):
    runtime = Gateway(context={"name": "old"})
    observed = {}

    def fake_execute(runtime_arg, path, *, context):
        runtime_arg.context.update(context)
        observed.update(path=path, context=context)
        return {}, "ok"

    monkeypatch.setattr("gway.sampler.execute_recipe", fake_execute)

    assert run(runtime, "web/expose", name="arthexis") == "ok"
    assert observed["path"] == resolve("web/expose")
    assert runtime.context["name"] == "arthexis"
