from gway import Gateway
from gway.recipe.resolve import resolve_recipe_stage
from gway.tokens import tokenize


def test_sampler_recipe_extends_loaded_operation_namespace():
    runtime = Gateway()
    tokens = tokenize("wire watchtower --public-address 192.0.2.10")
    resolved = resolve_recipe_stage(runtime, tokens, pipeline=None)
    assert resolved is not None
    path, arguments, remaining = resolved
    assert path.as_posix().endswith("/sampler/wire/watchtower.rx")
    assert [getattr(token, "value", token) for token in arguments] == [
        "--public-address", "192.0.2.10"
    ]
    assert remaining == []
    assert runtime.ops.resolve("wire.server.check") is not None


def test_exact_operation_still_shadows_sampler_recipe():
    runtime = Gateway()
    runtime.exact = runtime.wrap("wire.watchtower", lambda: "operation")
    tokens = tokenize("wire watchtower")
    assert resolve_recipe_stage(runtime, tokens, pipeline=None) is None


def test_project_root_recipe_resolves_as_bare_command(tmp_path, monkeypatch):
    recipe = tmp_path / "ci.rx"
    recipe.write_text("echo project-ci\\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    gateway = Gateway()

    tokens = tokenize("ci")
    resolved = resolve_recipe_stage(gateway, tokens, pipeline=None)

    assert resolved is not None
    path, arguments, remaining = resolved
    assert path == recipe
    assert arguments == []
    assert remaining == []


def test_gway_ci_recipe_uses_generic_recipe_and_test_contracts():
    from pathlib import Path

    recipe = Path("sampler/ci/__main__.rx").read_text(encoding="utf-8")

    assert "recipe check sampler" in recipe
    assert "test run - check --is 0" in recipe
    assert "github" not in recipe.lower()


def test_python_310_workflow_delegates_regression_to_project_ci():
    from pathlib import Path

    workflow = Path(".github/workflows/python-compatibility.yml").read_text(encoding="utf-8")

    regression, forward = workflow.split("  forward-compatibility:", 1)
    assert "INTEGRATION_PR:" in regression
    assert "WORKFLOW_PR:" in regression
    assert "github.event_name != 'pull_request'" in regression
    assert 'contains(github.event.pull_request.labels.*.name, \'integration\')' in regression
    assert 'contains(github.event.pull_request.labels.*.name, \'workflow\')' in regression
    assert "python -m gway ci" in regression
    assert "python -m gway test run architecture - check --is 0" in regression
    assert 'python -m gway test run --keyword "not architecture" - check --is 0' in regression
    assert "python -m pytest" not in regression
    assert "timeout -s ABRT 300s" in regression
    assert "PYTHONFAULTHANDLER" in regression
    assert "python -m pytest" in forward
    assert "push:" in workflow
    assert "branches: [main]" in workflow


def test_registered_operation_still_shadows_project_bare_recipe(tmp_path, monkeypatch):
    recipe = tmp_path / "status.rx"
    recipe.write_text("version\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    gateway = Gateway()
    gateway.status = gateway.wrap("status", lambda: "registered")

    assert resolve_recipe_stage(gateway, tokenize("status"), pipeline=None) is None


def test_project_bare_recipe_shadows_maintained_recipe_operation(tmp_path, monkeypatch):
    recipe = tmp_path / "ci.rx"
    recipe.write_text("resolve '[site|local]'\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    gateway = Gateway()

    # Expand the maintained sampler root so its first-class ci recipe is registered.
    gateway.operation_routes.expand(gateway, tokenize("ci"))
    maintained = gateway.ops.resolve("ci")
    assert maintained is not None
    assert getattr(maintained, "__gway_source_kind__", None) == "recipe"

    resolved = resolve_recipe_stage(gateway, tokenize("ci"), pipeline=None)

    assert resolved is not None
    path, arguments, remaining = resolved
    assert path == recipe
    assert arguments == []
    assert remaining == []


def test_semantic_pipeline_operation_shadows_project_bare_recipe(tmp_path, monkeypatch):
    recipe = tmp_path / "save.rx"
    recipe.write_text("version\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    gateway = Gateway()
    charger = object()
    gateway.results.insert("charger", charger)

    def save(charger):
        return charger

    gateway.save = gateway.wrap("save_charger", save, op="save", sub="charger")

    assert (
        resolve_recipe_stage(
            gateway,
            tokenize("save"),
            pipeline=charger,
        )
        is None
    )
