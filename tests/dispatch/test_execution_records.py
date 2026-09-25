from gway.execution import Execution


def test_execution_records_statement_subjects_and_results(gateway):
    gateway.first = gateway.wrap("read_status", lambda: "A")
    gateway.second = gateway.wrap("read_log", lambda: "B")

    assert gateway("first ; second") == {
        "results": [
            {"subject": "status", "result": "A"},
            {"subject": "log", "result": "B"},
        ]
    }

    execution = gateway.execution
    assert isinstance(execution, Execution)
    assert [statement.subject for statement in execution.statements] == [
        "status",
        "log",
    ]
    assert [statement.result for statement in execution.statements] == [
        "A",
        "B",
    ]


def test_pipeline_statement_uses_final_stage_subject_and_result(gateway):
    gateway.first = gateway.wrap("read_status", lambda: "A")
    gateway.second = gateway.wrap("inspect_log", lambda value: f"{value}:B")

    assert gateway("first - second") == "A:B"

    statement = gateway.execution.statements[0]
    assert statement.subject == "log"
    assert statement.result == "A:B"
    assert [stage.subject for stage in statement.stages] == ["status", "log"]


def test_statement_subject_does_not_depend_on_result_identity_lookup(gateway):
    shared = object()
    gateway.first = gateway.wrap("read_alpha", lambda: shared)
    gateway.second = gateway.wrap("read_beta", lambda: shared)

    gateway("first ; second")

    first, second = gateway.execution.statements
    assert first.result is shared
    assert second.result is shared
    assert first.subject == "alpha"
    assert second.subject == "beta"


def test_transparent_final_stage_is_not_marked_as_new_statement_publication(gateway):
    gateway.seed = gateway.wrap("read_seed", lambda: "A")

    gateway("seed")
    assert gateway("default --site MTY") == "A"

    statement = gateway.execution.statements[0]
    assert statement.published is False
    assert statement.subject is None
    assert statement.result is None


def test_empty_recipe_stage_is_not_a_phantom_publication(gateway, tmp_path):
    recipe = tmp_path / "empty.rx"
    recipe.write_text("", encoding="utf-8")

    assert gateway(recipe) is None

    statement = gateway.execution.statements[0]
    assert statement.published is False
    assert statement.subject is None
    assert statement.result is None


def test_transparent_recipe_final_stage_is_not_a_phantom_publication(
    gateway,
    tmp_path,
):
    recipe = tmp_path / "configure.rx"
    recipe.write_text("default --site MTY\n", encoding="utf-8")

    gateway(recipe)

    statement = gateway.previous_execution.statements[0]
    assert statement.published is False
    assert statement.subject is None
    assert statement.result is None
    assert gateway.context["site"] == "MTY"


def test_recipe_stage_uses_nested_final_semantic_subject(gateway, tmp_path):
    gateway.read = gateway.wrap("read_status", lambda: "ok")
    recipe = tmp_path / "probe.rx"
    recipe.write_text("read\n", encoding="utf-8")

    assert gateway(recipe) == "ok"

    statement = gateway.previous_execution.statements[0]
    assert statement.published is True
    assert statement.subject == "status"
    assert statement.result == "ok"


def test_presentation_results_preserve_repeated_subjects(gateway):
    gateway.first = gateway.wrap("read_status", lambda: "A")
    gateway.second = gateway.wrap("inspect_status", lambda: "B")

    result = gateway("first ; second")

    assert result == {
        "results": [
            {"subject": "status", "result": "A"},
            {"subject": "status", "result": "B"},
        ]
    }
    assert gateway.execution.presentation_results.getall("status") == ("A", "B")


def test_mixed_pipelines_aggregate_only_each_statement_final_result(gateway):
    gateway.first = gateway.wrap("read_alpha", lambda: "A")
    gateway.second = gateway.wrap("inspect_beta", lambda value: f"{value}B")
    gateway.third = gateway.wrap("read_gamma", lambda: "C")
    gateway.fourth = gateway.wrap("inspect_delta", lambda value: f"{value}D")
    gateway.fifth = gateway.wrap("read_epsilon", lambda: "E")

    assert gateway("first - second ; third - fourth ; fifth") == {
        "results": [
            {"subject": "beta", "result": "AB"},
            {"subject": "delta", "result": "CD"},
            {"subject": "epsilon", "result": "E"},
        ]
    }


def test_transparent_statement_does_not_force_aggregate(gateway):
    gateway.seed = gateway.wrap("read_seed", lambda: "A")

    assert gateway("seed ; default --site MTY") == "A"
    assert gateway.context["site"] == "MTY"


def test_nested_gateway_execution_remains_scalar(gateway):
    gateway.first = gateway.wrap("read_alpha", lambda: "A")
    gateway.second = gateway.wrap("read_beta", lambda: "B")

    def nested():
        return gateway("first ; second")

    gateway.nested = gateway.wrap("read_nested", nested)

    assert gateway("nested") == "B"


def test_recipe_with_multiple_statements_remains_scalar(gateway, tmp_path):
    gateway.first = gateway.wrap("read_alpha", lambda: "A")
    gateway.second = gateway.wrap("read_beta", lambda: "B")
    recipe = tmp_path / "multi.rx"
    recipe.write_text("first\nsecond\n", encoding="utf-8")

    assert gateway(recipe) == "B"
