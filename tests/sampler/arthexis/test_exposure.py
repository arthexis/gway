from pathlib import Path


def test_expose_defaults_to_inferred_web_binding(recipe_values):
    values = recipe_values("expose.rx")

    assert values[0] == [
        "default",
        "--name",
        "arthexis",
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
    ]
    assert values[1] == ["../web/expose/expose"]


def test_expose_leaves_public_identity_to_caller():
    text = Path("sampler/arthexis/expose.rx").read_text(encoding="utf-8")
    prefix = text.split("../web/expose/expose", 1)[0]

    assert "--domain" not in prefix
    assert "--email" not in prefix


def test_dns_exposure_is_explicit_and_composed(recipe_values):
    values = recipe_values("dns-expose.rx")

    assert ["../web/expose/dns-http"] in values
    assert ["./expose"] in values
