from pathlib import Path


def _commands(name):
    from gway.recipe import load_recipe
    from gway.tokens import token_value

    root = Path(__file__).resolve().parents[2] / "sampler" / "wire"
    commands, _ = load_recipe(root / name)
    return [
        [token_value(token) for token in command["tokens"]]
        for command in commands
    ]


def test_wire_enroll_recipe_runs_server_with_watchtower_defaults():
    values = _commands("enroll.rx")

    flattened = [" ".join(command) for command in values]
    assert any("wire server serve" in command for command in flattened)
    assert any("register.arthexis.com" in command for command in flattened)
    assert any("vpn.arthexis.com:51820" in command for command in flattened)


def test_wire_watchtower_recipe_composes_service_and_https_exposure():
    values = _commands("watchtower.rx")
    flattened = [" ".join(command) for command in values]

    assert any(command.startswith("wire server deploy") for command in flattened)
    assert any(command.startswith("service install") for command in flattened)
    assert any("wire-enroll" in command for command in flattened)
    assert any(command.startswith("service start") for command in flattened)
    assert any("../web/expose/expose" in command for command in flattened)
    assert any(command.startswith("wire server check") for command in flattened)


def test_wire_watchtower_recipe_uses_existing_register_hostname():
    values = _commands("watchtower.rx")
    flattened = "\n".join(" ".join(command) for command in values)

    assert "register.arthexis.com" in flattened
    assert "register-wire.arthexis.com" not in flattened
