import runpy


def test_gway_bootstrap_excludes_obsolete_release_during_rollout(sampler_path):
    script = sampler_path("bootstrap/gway.sh").read_text(encoding="utf-8")

    assert script.startswith("#!/bin/sh\n# GWAY_BOOTSTRAP_V1\n")
    assert "uv/install.sh" in script
    assert 'tool install --force --upgrade "gway!=1.0.*"' in script
    assert "gway<1" not in script
    assert 'tool install --force --upgrade gway' not in script
    assert "gway!=1.0.1" not in script
    assert "git+https://github.com/arthexis/gway" not in script
    assert "tool install --upgrade gway" not in script


def test_gway_bootstrap_persists_tool_path_and_smoke_checks_cli(sampler_path):
    script = sampler_path("bootstrap/gway.sh").read_text(encoding="utf-8")

    assert 'TOOL_BIN="$("$UV" tool dir --bin)"' in script
    assert script.index('"$UV" tool update-shell') < script.index('export PATH="$TOOL_BIN:$PATH"')
    assert 'export PATH="$TOOL_BIN:$PATH"' in script
    assert 'elif test -x "$TOOL_BIN/gway"; then' in script
    assert 'GWAY="$TOOL_BIN/gway"' in script
    assert '"$GWAY" --help >/dev/null' in script
    assert '"$UV" tool update-shell >/dev/null 2>&1 || true' not in script
    assert "could not persist tool PATH for future shells" in script
    assert '"$GWAY" version' not in script
    assert "already-running parent shell" in script or "cannot mutate its parent" in script


def test_watchtower_bootstrap_recipe_owns_installer_site_dns_and_tls(recipe_commands):
    commands = recipe_commands("bootstrap/watchtower.rx")
    rendered = "\n".join(commands)

    assert "install.arthexis.com" in rendered
    assert "watchtower catalog" in commands
    assert any(command.startswith("render installer.html") for command in commands)
    assert any(command.startswith("render gway.sh") for command in commands)
    assert commands.count("watchtower installer satellite") == 1
    assert commands.count("watchtower installer control") == 1
    assert sum(command.startswith("render arthexis.sh") for command in commands) == 2
    assert any(command.startswith("dns create [domain]") for command in commands)
    assert any(command.startswith("dns ready [domain]") for command in commands)
    assert any(command.startswith("certbot certonly") for command in commands)
    assert any(
        command.startswith("render nginx-https-[site].conf")
        for command in commands
    )
    assert commands[-1] == "commit gway-bootstrap"


def test_installer_catalog_is_single_source_for_public_choices(sampler_path):
    namespace = runpy.run_path(str(sampler_path("bootstrap/watchtower.py")))
    catalog = namespace["catalog"]()["installers"]

    assert [item["installer"] for item in catalog] == [
        "gway",
        "satellite",
        "control",
    ]
    assert [item["title"] for item in catalog] == [
        "GWAY",
        "Satellite",
        "Control",
    ]
    assert all(item["description"] for item in catalog)
    assert all("url" not in item and "command" not in item for item in catalog)


def test_installer_page_derives_endpoint_and_command_from_installer(sampler_path):
    page = sampler_path("bootstrap/installer.html").read_text(encoding="utf-8")

    assert "[installers_json]" in page
    assert 'new URL("/" + installer, window.location.origin).href' in page
    assert '"curl -fsSL " + endpoint(installer) + " | sh"' in page
    assert 'searchParams.get("box")' in page
    assert 'searchParams.set("box", item.installer)' in page
    assert 'searchParams.delete("box")' in page
    assert "location.hash" not in page
    assert "navigator.clipboard.writeText" in page
    assert "Install other projects" in page
    assert "https://install.arthexis.com" not in page


def test_arthexis_roles_share_one_installer_template(sampler_path):
    script = sampler_path("bootstrap/arthexis.sh").read_text(encoding="utf-8")

    assert 'curl -fsSL "https://[domain]/gway" | sh' in script
    assert 'TOOL_BIN="$("$UV" tool dir --bin)"' in script
    assert 'if test -x "$TOOL_BIN/gway"; then' in script
    assert 'GWAY="$TOOL_BIN/gway"' in script
    assert 'command -v gway' not in script
    assert '"$GWAY" install arthexis/arthexis' in script
    assert '"$GWAY" arthexis migrate --noinput' in script
    assert '"$GWAY" arthexis seed' in script
    assert "[installer_title]" in script
    assert "[installer_description]" in script
    assert "satellite" not in script.lower()
    assert "control" not in script.lower()


def test_bootstrap_https_site_serves_ui_and_exact_installer_paths(sampler_path):
    nginx = sampler_path("bootstrap/nginx-https-[site].conf").read_text(
        encoding="utf-8"
    )

    assert "location = / {" in nginx
    assert "location = /gway" in nginx
    assert "location = /satellite" in nginx
    assert "location = /control" in nginx
    assert nginx.count('Cache-Control "no-store"') == 4
    assert nginx.count('Strict-Transport-Security "max-age=31536000" always') == 5
    assert nginx.count('X-Content-Type-Options "nosniff" always') == 5
    assert nginx.count('Referrer-Policy "same-origin" always') == 5
    assert "location / {" in nginx
    assert "return 404;" in nginx
