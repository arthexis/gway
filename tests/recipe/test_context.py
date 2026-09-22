def test_recipe_flags_extend_shared_context(gateway, recipe_factory):
    gateway.show_site = gateway.wrap("show_site", lambda site: site)
    recipe = recipe_factory(name="show", body="show site\n")

    assert gateway(f"{recipe} --site MTY") == "MTY"
    assert gateway.context["site"] == "MTY"


def test_bare_recipe_flag_sets_boolean_true_in_shared_context(
    gateway, recipe_factory
):
    gateway.show_enabled = gateway.wrap("show_enabled", lambda enabled: enabled)
    recipe = recipe_factory(name="enabled", body="show enabled\n")

    assert gateway(f"{recipe} --enabled") is True
    assert gateway.context["enabled"] is True


def _install_probe(gateway, captured):
    def install_project(*, role="Watchtower"):
        captured["role"] = role
        return role

    gateway.install_project = gateway.wrap("install_project", install_project)


def test_recipe_context_resolves_sigil_before_operation(gateway, recipe_factory):
    captured = {}
    _install_probe(gateway, captured)
    recipe = recipe_factory(
        name="bootstrap",
        body="install project --role [role|Watchtower]\n",
    )

    assert gateway(f"{recipe} --role Satellite") == "Satellite"
    assert captured["role"] == "Satellite"


def test_recipe_context_uses_inline_fallback(gateway, recipe_factory):
    captured = {}
    _install_probe(gateway, captured)
    recipe = recipe_factory(
        name="bootstrap",
        body="install project --role [role|Watchtower]\n",
    )

    assert gateway(recipe) == "Watchtower"
    assert captured["role"] == "Watchtower"


def test_explicit_operation_argument_wins_over_recipe_context(
    gateway, recipe_factory
):
    captured = {}
    _install_probe(gateway, captured)
    recipe = recipe_factory(
        name="bootstrap",
        body="install project --role Control\n",
    )

    assert gateway(f"{recipe} --role Satellite") == "Control"
    assert captured["role"] == "Control"
