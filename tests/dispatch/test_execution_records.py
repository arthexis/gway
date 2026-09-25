from gway.execution import Execution


def test_execution_records_statement_subjects_and_results(gateway):
    gateway.first = gateway.wrap("read_status", lambda: "A")
    gateway.second = gateway.wrap("read_log", lambda: "B")

    assert gateway("first ; second") == "B"

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


def test_empty_recipe_stage_is_not_a_phantom_publication(gateway, recipe_factory):
    recipe = recipe_factory(name="empty", body="")

    assert gateway(recipe) is None

    statement = gateway.execution.statements[0]
    assert statement.published is False
    assert statement.subject is None
    assert statement.result is None


def test_transparent_recipe_final_stage_is_not_a_phantom_publication(
    gateway,
    recipe_factory,
):
    recipe = recipe_factory(name="configure", body="default --site MTY\n")

    gateway(recipe)

    statement = gateway.previous_execution.statements[0]
    assert statement.published is False
    assert statement.subject is None
    assert statement.result is None
    assert gateway.context["site"] == "MTY"


def test_recipe_stage_uses_nested_final_semantic_subject(gateway, recipe_factory):
    gateway.read = gateway.wrap("read_status", lambda: "ok")
    recipe = recipe_factory(name="probe", body="read\n")

    assert gateway(recipe) == "ok"

    statement = gateway.previous_execution.statements[0]
    assert statement.published is True
    assert statement.subject == "status"
    assert statement.result == "ok"
