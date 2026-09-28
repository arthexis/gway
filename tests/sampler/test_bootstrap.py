def test_gway_bootstrap_installs_only_released_package(sampler_path):
    script = sampler_path("bootstrap/gway.sh").read_text(encoding="utf-8")

    assert script.startswith("#!/bin/sh\n# GWAY_BOOTSTRAP_V1\n")
    assert "uv/install.sh" in script
    assert 'tool install --upgrade gway' in script
    assert "git+https://github.com/arthexis/gway" not in script


def test_gway_bootstrap_persists_tool_path_and_smoke_checks_cli(sampler_path):
    script = sampler_path("bootstrap/gway.sh").read_text(encoding="utf-8")

    assert 'TOOL_BIN="$("$UV" tool dir --bin)"' in script
    assert script.index('"$UV" tool update-shell') < script.index('export PATH="$TOOL_BIN:$PATH"')
    assert 'export PATH="$TOOL_BIN:$PATH"' in script
    assert 'elif test -x "$TOOL_BIN/gway"; then' in script
    assert 'GWAY="$TOOL_BIN/gway"' in script
    assert '"$GWAY" --help >/dev/null' in script
    assert '"$GWAY" version' not in script
    assert "already-running parent shell" in script or "cannot mutate its parent" in script


def test_watchtower_bootstrap_recipe_owns_dns_tls_and_static_site(recipe_commands):
    commands = recipe_commands("bootstrap/watchtower.rx")
    rendered = "\n".join(commands)

    assert "install.arthexis.com" in rendered
    assert any(command.startswith("dns create [domain]") for command in commands)
    assert any(command.startswith("dns ready [domain]") for command in commands)
    assert any(command.startswith("render gway.sh") for command in commands)
    assert any(command.startswith("certbot certonly") for command in commands)
    assert any(
        command.startswith("render nginx-https-[site].conf")
        for command in commands
    )
    assert commands[-1] == "commit gway-bootstrap"


def test_bootstrap_https_site_only_serves_exact_gway_path(sampler_path):
    nginx = sampler_path("bootstrap/nginx-https-[site].conf").read_text(
        encoding="utf-8"
    )

    assert "location = /gway" in nginx
    assert 'Cache-Control "no-store"' in nginx
    assert "location / {" in nginx
    assert "return 404;" in nginx
