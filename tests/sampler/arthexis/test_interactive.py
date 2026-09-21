def test_interactive_prompts_for_required_deployment_values(recipe_values):
    values = recipe_values("interactive.rx")

    assert values[:4] == [
        ["input", "Arthexis secret key", "--as", "arthexis_secret_key", "--secret"],
        [
            "secret",
            "env",
            "arthexis",
            "ARTHEXIS_SECRET_KEY",
            "[arthexis_secret_key]",
        ],
        ["input", "Public domain", "--as", "domain"],
        ["input", "TLS contact email", "--as", "email"],
    ]
    assert ["./setup"] in values
    assert ["./expose"] in values


def test_interactive_keeps_dns_opt_in(recipe_values):
    assert ["./dns-expose"] not in recipe_values("interactive.rx")
