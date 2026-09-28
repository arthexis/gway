from gway.gateway import Gateway
import pytest


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


def test_source_search_finds_python_match_with_absolute_line(gateway):
    source = gateway("source env")
    result = gateway("source env --search Return --context 1")

    assert result["operation"] == "env"
    assert result["kind"] == "python"
    assert len(result["matches"]) == 1
    match = result["matches"][0]
    assert match["line"] >= source["start_line"]
    assert "Return" in match["text"]
    assert len(match["before"]) <= 1
    assert len(match["after"]) <= 1


def test_source_search_finds_multiple_matches(gateway):
    result = gateway("source env --search default --context 0")

    assert len(result["matches"]) >= 2
    assert all("default" in match["text"] for match in result["matches"])
    assert all(match["before"] == [] for match in result["matches"])
    assert all(match["after"] == [] for match in result["matches"])


def test_source_search_returns_empty_matches_without_widening(gateway):
    result = gateway("source env --search definitely_not_in_env_source")

    assert result["operation"] == "env"
    assert result["matches"] == []
    assert "source" not in result


def test_source_search_finds_recipe_match(gateway, tmp_path):
    root = tmp_path / "recipes"
    recipe = root / "deploy.rx"
    root.mkdir()
    recipe.write_text(
        "env FIRST\nservice install web\nenv LAST\n",
        encoding="utf-8",
    )
    gateway.ingest(root)

    result = gateway("source recipes deploy --search service --context 1")

    assert result["kind"] == "recipe"
    assert result["path"] == str(recipe)
    assert result["matches"] == [
        {
            "line": 2,
            "text": "service install web",
            "before": ["env FIRST"],
            "after": ["env LAST"],
        }
    ]


def test_search_source_finds_registered_python_operations(gateway):
    results = gateway("search source Return --kind python")

    assert any(item["operation"] == "env" for item in results)
    assert all(item["kind"] == "python" for item in results)
    assert all("source" not in item for item in results)


def test_search_source_kind_filter_excludes_python(gateway):
    results = gateway("search source Return --kind recipe")

    assert not any(item["operation"] == "env" for item in results)


def test_search_source_filters_explicit_topics_as_intersection(gateway):
    operation = gateway.ops.resolve("env")
    operation.__gway_metadata__ = {"topics": ("remote", "log")}

    from gway.source import search_source_corpus

    forward = search_source_corpus(
        gateway, "Return", topic=("remote", "log")
    )
    reverse = search_source_corpus(
        gateway, "Return", topic=("log", "remote")
    )

    assert [item["operation"] for item in forward] == [
        item["operation"] for item in reverse
    ]
    assert any(item["operation"] == "env" for item in forward)


def test_search_source_topic_does_not_match_source_text(gateway):
    operation = gateway.ops.resolve("env")
    operation.__gway_metadata__ = {"topics": ()}

    results = gateway("search source Return --topic remote")

    assert not any(item["operation"] == "env" for item in results)


def test_source_authorization_requires_source_and_target_visibility(gateway):
    from gway.authorization import AuthorizationError

    with gateway.authorized(operations={"source", "env"}):
        assert gateway("source env")["operation"] == "env"

    with gateway.authorized(operations={"source"}):
        with pytest.raises(AuthorizationError):
            gateway("source env")


def test_source_authorization_requires_source_capability(gateway):
    from gway.authorization import AuthorizationError

    with gateway.authorized(operations={"env"}):
        with pytest.raises(AuthorizationError):
            gateway("source env")


def test_search_source_excludes_hidden_operations(gateway):
    with gateway.authorized(operations={"search.source", "env"}):
        results = gateway("search source Return")

    assert any(item["operation"] == "env" for item in results)
    assert all(item["operation"].replace(" ", ".") in {"search.source", "env"} for item in results)


def test_search_source_requires_source_search_capability(gateway):
    from gway.authorization import AuthorizationError

    with gateway.authorized(operations={"env"}):
        with pytest.raises(AuthorizationError):
            gateway("search source Return")


def test_source_all_reports_selected_and_shadowed_in_resolver_order(gateway):
    def first():
        return "first"

    def second():
        return "second"

    def selected():
        return "selected"

    gateway.wrap("diagnostic.target", first)
    gateway.wrap("diagnostic.target", second)
    gateway.wrap("diagnostic.target", selected)

    result = gateway("source diagnostic target --all")

    assert result["operation"] == "diagnostic target"
    assert "selected" in result["selected"]["source"]
    assert len(result["shadowed"]) == 2
    assert "second" in result["shadowed"][0]["source"]
    assert "first" in result["shadowed"][1]["source"]


def test_source_without_all_reports_only_selected_candidate(gateway):
    def old():
        return "old"

    def current():
        return "current"

    gateway.wrap("diagnostic.single", old)
    gateway.wrap("diagnostic.single", current)

    result = gateway("source diagnostic single")

    assert "current" in result["source"]
    assert "shadowed" not in result


def test_source_all_does_not_change_normal_resolution(gateway):
    def old():
        return "old"

    def current():
        return "current"

    gateway.wrap("diagnostic.execute", old)
    gateway.wrap("diagnostic.execute", current)

    gateway("source diagnostic execute --all")

    assert gateway("diagnostic execute") == "current"


def test_source_all_respects_target_visibility(gateway):
    from gway.authorization import AuthorizationError

    def hidden():
        return "hidden"

    gateway.wrap("diagnostic.hidden", hidden)

    with gateway.authorized(operations={"source"}):
        with pytest.raises(AuthorizationError):
            gateway("source diagnostic hidden --all")


def test_source_all_rejects_search_combination(gateway):
    with pytest.raises(TypeError, match="cannot be combined"):
        gateway("source env --all --search Return")
