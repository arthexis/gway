from pathlib import Path


def test_setup_uses_overrideable_ref_default(recipe_values):
    values = recipe_values("setup.rx")

    assert values[0] == ["default", "--ref", "arthexis-rebuild"]
    assert values[1] == ["install", "arthexis/arthexis"]


def test_setup_prepares_django_after_install(recipe_values):
    values = recipe_values("setup.rx")

    assert ["arthexis", "migrate", "--noinput"] in values
    assert ["arthexis", "seed"] in values
    assert values.index(["arthexis", "seed"]) > values.index(
        ["arthexis", "migrate", "--noinput"]
    )


def test_setup_uses_inferred_service_targets(recipe_values):
    values = recipe_values("setup.rx")

    for action in ("install", "start"):
        for service in ("web", "worker", "beat"):
            assert ["service", action, "--", "arthexis", service] in values


def test_setup_does_not_duplicate_runtime_commands():
    text = Path("sampler/arthexis/setup.rx").read_text(encoding="utf-8")

    assert "daphne" not in text
    assert "celery" not in text


def test_setup_keeps_system_scope_implicit(recipe_values):
    values = recipe_values("setup.rx")

    assert all("--system" not in command for command in values)
