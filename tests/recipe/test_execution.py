import pytest


@pytest.mark.parametrize(
    "reference",
    [
        pytest.param(lambda path: path, id="path-object"),
        pytest.param(str, id="string-path"),
    ],
)
def test_gateway_executes_recipe_from_explicit_path_reference(
    gateway, recipe_factory, reference
):
    gateway.echo = gateway.wrap("echo_value", lambda value: value)
    recipe = recipe_factory(body="echo hello\n")

    assert gateway(reference(recipe)) == "hello"


def test_bare_existing_recipe_is_fallback_when_operation_is_missing(
    gateway, recipe_factory, monkeypatch, tmp_path
):
    gateway.echo = gateway.wrap("echo_value", lambda value: value)
    recipe_factory(name="nightly", body="echo recipe\n")
    monkeypatch.chdir(tmp_path)

    assert gateway("nightly") == "recipe"


def test_registered_operation_beats_ambiguous_bare_recipe(
    gateway, recipe_factory, monkeypatch, tmp_path
):
    gateway.deploy = gateway.wrap("deploy", lambda: "operation")
    gateway.echo = gateway.wrap("echo_value", lambda value: value)
    recipe_factory(name="deploy", body="echo recipe\n")
    monkeypatch.chdir(tmp_path)

    assert gateway("deploy") == "operation"


def test_explicit_recipe_path_beats_same_named_operation(
    gateway, recipe_factory, monkeypatch, tmp_path
):
    gateway.deploy = gateway.wrap("deploy", lambda: "operation")
    gateway.echo = gateway.wrap("echo_value", lambda value: value)
    recipe = recipe_factory(name="deploy", body="echo recipe\n")
    monkeypatch.chdir(tmp_path)

    assert gateway(f"./{recipe.name}") == "recipe"


def test_recipe_final_result_can_feed_following_pipeline_stage(
    gateway, recipe_factory
):
    gateway.pair = gateway.wrap("get_pair", lambda: ("A", "B"))

    def combine(first, second, third):
        return first, second, third

    gateway.combine = gateway.wrap("combine_values", combine)
    recipe = recipe_factory(name="pair", body="pair\n")

    assert gateway(f"{recipe} - combine C") == ("A", "B", "C")



def test_recipe_publications_remain_available_after_recipe_returns(
    gateway, recipe_factory
):
    gateway.load_config = gateway.wrap(
        "load_config",
        lambda: {"site": "MTY"},
    )
    gateway.make_report = gateway.wrap("make_report", lambda: "report")

    def consume(report, site):
        return report, site

    gateway.consume = gateway.wrap("consume_report", consume)
    recipe = recipe_factory(
        name="prepare",
        body="load config\nmake report\n",
    )

    assert gateway(f"{recipe} - consume") == ("report", "MTY")

def test_pipeline_can_feed_first_statement_of_recipe(gateway, recipe_factory):
    marker = object()
    gateway.produce = gateway.wrap("produce_value", lambda: marker)
    gateway.consume = gateway.wrap("consume_value", lambda value: value)
    recipe = recipe_factory(name="consume", body="consume\n")

    assert gateway(f"produce - {recipe}") is marker


def test_nested_relative_recipe_resolves_from_containing_recipe(
    gateway, recipe_factory, tmp_path, monkeypatch
):
    gateway.echo = gateway.wrap("echo_value", lambda value: value)
    root = tmp_path / "recipes"
    inner = recipe_factory("inner", "echo nested\n", root=root)
    outer = recipe_factory("outer", "./inner.rx\n", root=root)

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    assert gateway(outer) == "nested"
    assert inner.is_file()


def test_recursive_recipe_cycle_is_rejected(gateway, recipe_factory):
    first = recipe_factory("first", "./second.rx\n")
    recipe_factory("second", "./first.rx\n")

    with pytest.raises(RuntimeError, match="Recipe cycle"):
        gateway(first)


def test_recipe_without_companion_executes_normally(gateway, recipe_factory):
    gateway.echo = gateway.wrap("echo_value", lambda value: value)
    recipe = recipe_factory(name="plain", body="echo ok\n")

    assert gateway(recipe) == "ok"
