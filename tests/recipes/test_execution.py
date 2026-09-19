from pathlib import Path

import pytest


def test_gateway_executes_recipe_from_path_object(gateway, tmp_path):
    def echo(value):
        return value

    gateway.echo = gateway.wrap("echo_value", echo)
    recipe = tmp_path / "simple.rx"
    recipe.write_text("echo hello\n", encoding="utf-8")

    assert gateway(recipe) == "hello"


def test_gateway_executes_recipe_from_explicit_string_path(gateway, tmp_path):
    def echo(value):
        return value

    gateway.echo = gateway.wrap("echo_value", echo)
    recipe = tmp_path / "simple.rx"
    recipe.write_text("echo hello\n", encoding="utf-8")

    assert gateway(str(recipe)) == "hello"


def test_bare_existing_recipe_is_fallback_when_operation_is_missing(
    gateway,
    tmp_path,
    monkeypatch,
):
    def echo(value):
        return value

    gateway.echo = gateway.wrap("echo_value", echo)
    recipe = tmp_path / "nightly"
    recipe.write_text("echo recipe\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert gateway("nightly") == "recipe"


def test_registered_operation_beats_ambiguous_bare_recipe(
    gateway,
    tmp_path,
    monkeypatch,
):
    def deploy():
        return "operation"

    def echo(value):
        return value

    gateway.deploy = gateway.wrap("deploy", deploy)
    gateway.echo = gateway.wrap("echo_value", echo)
    recipe = tmp_path / "deploy"
    recipe.write_text("echo recipe\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert gateway("deploy") == "operation"


def test_explicit_recipe_path_beats_same_named_operation(
    gateway,
    tmp_path,
    monkeypatch,
):
    def deploy():
        return "operation"

    def echo(value):
        return value

    gateway.deploy = gateway.wrap("deploy", deploy)
    gateway.echo = gateway.wrap("echo_value", echo)
    recipe = tmp_path / "deploy"
    recipe.write_text("echo recipe\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert gateway("./deploy") == "recipe"


def test_recipe_final_result_can_feed_following_pipeline_stage(gateway, tmp_path):
    def pair():
        return ("A", "B")

    def combine(first, second, third):
        return first, second, third

    gateway.pair = gateway.wrap("get_pair", pair)
    gateway.combine = gateway.wrap("combine_values", combine)
    recipe = tmp_path / "pair.rx"
    recipe.write_text("pair\n", encoding="utf-8")

    assert gateway(f"{recipe} - combine C") == ("A", "B", "C")


def test_recipe_publications_remain_available_after_recipe_returns(gateway, tmp_path):
    def load_config():
        return {"site": "MTY"}

    def make_report():
        return "report"

    def consume(report, site):
        return report, site

    gateway.load_config = gateway.wrap("load_config", load_config)
    gateway.make_report = gateway.wrap("make_report", make_report)
    gateway.consume = gateway.wrap("consume_report", consume)
    recipe = tmp_path / "prepare.rx"
    recipe.write_text(
        "load config\n"
        "make report\n",
        encoding="utf-8",
    )

    assert gateway(f"{recipe} - consume") == ("report", "MTY")


def test_pipeline_can_feed_first_statement_of_recipe(gateway, tmp_path):
    marker = object()

    def produce():
        return marker

    def consume(value):
        return value

    gateway.produce = gateway.wrap("produce_value", produce)
    gateway.consume = gateway.wrap("consume_value", consume)
    recipe = tmp_path / "consume.rx"
    recipe.write_text("consume\n", encoding="utf-8")

    assert gateway(f"produce - {recipe}") is marker


def test_nested_relative_recipe_resolves_from_containing_recipe(
    gateway,
    tmp_path,
    monkeypatch,
):
    def echo(value):
        return value

    gateway.echo = gateway.wrap("echo_value", echo)
    recipes = tmp_path / "recipes"
    recipes.mkdir()
    inner = recipes / "inner.rx"
    outer = recipes / "outer.rx"
    inner.write_text("echo nested\n", encoding="utf-8")
    outer.write_text("./inner.rx\n", encoding="utf-8")

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    assert gateway(outer) == "nested"


def test_recursive_recipe_cycle_is_rejected(gateway, tmp_path):
    first = tmp_path / "first.rx"
    second = tmp_path / "second.rx"
    first.write_text("./second.rx\n", encoding="utf-8")
    second.write_text("./first.rx\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="Recipe cycle"):
        gateway(first)


def test_recipe_flags_extend_shared_context(gateway, tmp_path):
    def show_site(site):
        return site

    gateway.show_site = gateway.wrap("show_site", show_site)
    recipe = tmp_path / "show.rx"
    recipe.write_text("show site\n", encoding="utf-8")

    assert gateway(f"{recipe} --site MTY") == "MTY"
    assert gateway.context["site"] == "MTY"
