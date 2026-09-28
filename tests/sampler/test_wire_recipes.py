def test_wire_enroll_recipe_runs_server_with_watchtower_defaults(recipe_commands):
    values = recipe_commands("wire/enroll.rx")

    flattened = values
    assert any("wire server serve" in command for command in flattened)
    assert any("register.arthexis.com" in command for command in flattened)
    assert any("vpn.arthexis.com:51820" in command for command in flattened)


def test_wire_watchtower_recipe_composes_service_and_https_exposure(recipe_commands):
    values = recipe_commands("wire/watchtower.rx")
    flattened = values

    assert any(command.startswith("wire server deploy") for command in flattened)
    assert any(command.startswith("wire server activate") for command in flattened)
    assert any(command.startswith("service install") for command in flattened)
    assert any("wire-enroll" in command for command in flattened)
    assert any(command.startswith("service start") for command in flattened)
    assert any("../web/expose/expose" in command for command in flattened)
    assert any(command.startswith("wire server check") for command in flattened)
    deploy_index = next(
        index
        for index, command in enumerate(flattened)
        if command.startswith("wire server deploy")
    )
    activate_index = next(
        index
        for index, command in enumerate(flattened)
        if command.startswith("wire server activate")
    )
    commit_index = next(
        index
        for index, command in enumerate(flattened)
        if command.startswith("commit wire-watchtower")
    )
    deploy = flattened[deploy_index]
    commit = flattened[commit_index]
    assert "--sudo" in deploy
    assert "--rollback wire-watchtower" in deploy
    assert deploy_index < activate_index < commit_index
    assert commit == "commit wire-watchtower"


def test_wire_watchtower_recipe_uses_existing_register_hostname(recipe_commands):
    values = recipe_commands("wire/watchtower.rx")
    flattened = "\n".join(command for command in values)

    assert "register.arthexis.com" in flattened
    assert "register-wire.arthexis.com" not in flattened


def test_wire_recipes_do_not_require_data_dir_sigil(recipe_commands):
    rendered = "\n".join(
        command
        for name in ("enroll.rx", "watchtower.rx")
        for command in recipe_commands(f"wire/{name}")
    )
    assert "[data_dir]" not in rendered


def test_wire_watchtower_recipe_does_not_require_explicit_server_keys(recipe_commands):
    rendered = "\n".join(
        command
        for name in ("enroll.rx", "watchtower.rx")
        for command in recipe_commands(f"wire/{name}")
    )
    assert "--private-key" not in rendered
    assert "--server-public-key" not in rendered


def test_wire_watchtower_reclaims_listener_before_service_start(recipe_commands):
    values = recipe_commands("wire/watchtower.rx")
    flattened = values

    reclaim_index = next(
        index
        for index, command in enumerate(flattened)
        if command.startswith("wire server reclaim")
    )
    start_index = next(
        index
        for index, command in enumerate(flattened)
        if command.startswith("service start")
    )

    assert reclaim_index < start_index
    assert "--host [host]" in flattened[reclaim_index]
    assert "--port [port]" in flattened[reclaim_index]
