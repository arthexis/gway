from gway.logs.registry import recipe_sources, register_recipe_source


def test_recipe_log_source_registry_persists_across_invocations(tmp_path):
    first = register_recipe_source("recipe/watchtower", root=tmp_path)

    assert first == "recipe/watchtower"
    assert [source.identity for source in recipe_sources(tmp_path)] == [
        "recipe/watchtower"
    ]

    # Re-registration is idempotent and another process can rediscover it.
    register_recipe_source("watchtower", root=tmp_path)
    discovered = recipe_sources(tmp_path)

    assert len(discovered) == 1
    assert discovered[0].kind == "recipe"
    assert discovered[0].backend == "journal"
    assert discovered[0].backend_id == "recipe/watchtower"


def test_recipe_log_source_registry_merges_readable_roots(tmp_path):
    user = tmp_path / "user"
    system = tmp_path / "system"
    register_recipe_source("deploy", root=user)
    register_recipe_source("watchtower", root=system)

    assert [source.identity for source in recipe_sources(user, system)] == [
        "recipe/deploy",
        "recipe/watchtower",
    ]
