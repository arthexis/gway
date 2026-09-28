from gway.gateway import Gateway


def test_source_inspects_resolved_python_operation(gateway):
    result = gateway("source env")

    assert result["operation"] == "env"
    assert result["kind"] == "python"
    assert result["available"] is True
    assert result["path"].endswith("gway/builtin.py")
    assert "def env(" in result["source"]
    assert result["start_line"] <= result["end_line"]


def test_source_uses_normal_longest_operation_resolution(gateway):
    result = gateway("source toml loads")

    assert result["operation"] in {"toml loads", "toml_loads", "toml.loads"}
    assert result["kind"] == "python"
    assert "def loads(" in result["source"]


def test_source_inspects_ingested_recipe(gateway, tmp_path):
    root = tmp_path / "recipes"
    recipe = root / "status.rx"
    root.mkdir()
    recipe.write_text("env GWAY_SOURCE_TEST\n", encoding="utf-8")
    gateway.ingest(root)

    result = gateway("source recipes status")

    assert result == {
        "operation": "recipes status",
        "kind": "recipe",
        "source": "env GWAY_SOURCE_TEST\n",
        "path": str(recipe),
        "start_line": 1,
        "end_line": 1,
        "available": True,
        "reason": None,
    }


def test_source_is_non_mutating(gateway):
    operation = gateway.ops.resolve("source")

    assert operation.mutates is False
    result = gateway.execute("source env", mutate=False)
    assert result["operation"] == "env"


def test_source_reports_unavailable_dynamic_callable(gateway):
    namespace = {}
    exec("def dynamic():\n    return 1\n", namespace)
    gateway.dynamic = gateway.wrap("dynamic", namespace["dynamic"])

    result = gateway("source dynamic")

    assert result["operation"] == "dynamic"
    assert result["kind"] == "python"
    assert result["available"] is False
    assert result["source"] is None
    assert result["reason"]
