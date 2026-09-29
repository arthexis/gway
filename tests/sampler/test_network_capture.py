def test_network_capture_recipe_uses_owned_redirect_primitive(recipe_commands):
    commands = recipe_commands("network/capture.rx")

    redirect = next(
        command for command in commands if command.startswith("network redirect")
    )
    assert "--target [target]" in redirect
    assert "--target-port [target_port]" in redirect
    assert "--sudo" in redirect
    assert "nft" not in redirect
    assert "iptables" not in redirect
