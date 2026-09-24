from pathlib import Path

import pytest

from gway.recipe import load_recipe, recipe_path

def remote_root():
    return Path(__file__).resolve().parents[2] / "sampler" / "web" / "remote"

def _template(name):
    return (remote_root() / name).read_text(encoding="utf-8")

def _commands(name):
    commands, _ = load_recipe(remote_root() / name)
    return [" ".join(str(token) for token in command["tokens"]) for command in commands]

def _block(content, marker):
    start = content.index(marker)
    next_location = content.find("\n    location ", start + len(marker))
    next_server = content.find("\n}", start + len(marker))
    candidates = [item for item in (next_location, next_server) if item >= 0]
    end = min(candidates) if candidates else len(content)
    return content[start:end]

def test_remote_proxy_package_has_topology_templates():
    root = remote_root()

    assert (root / "nginx-http-[site].conf").is_file()
    assert (root / "nginx-https-[site].conf").is_file()

def test_remote_https_template_uses_two_independent_loopback_upstreams():
    content = _template("nginx-https-[site].conf")

    assert "proxy_pass http://[mcp_host|127.0.0.1]:[mcp_port|8000];" in content
    assert "proxy_pass http://[auth_host|127.0.0.1]:[auth_port|8001];" in content

    mcp = _block(content, "location = /mcp {")
    assert "[mcp_host|127.0.0.1]:[mcp_port|8000]" in mcp
    assert "[auth_host|127.0.0.1]:[auth_port|8001]" not in mcp

def test_remote_https_template_routes_public_oauth_surface_to_remote_auth():
    content = _template("nginx-https-[site].conf")
    auth_target = "[auth_host|127.0.0.1]:[auth_port|8001]"

    for marker in (
        "location = / {",
        "location = /query {",
        "location = /.well-known/oauth-protected-resource/mcp {",
        "location = /.well-known/oauth-authorization-server {",
        "location = /.well-known/gway-acceptance-client {",
        "location = /oauth/authorize {",
        "location = /oauth/token {",
        "location = /oauth/revoke {",
        "location = /login {",
        "location = /connect {",
        "location = /consent {",
        "location = /settings/connections {",
    ):
        block = _block(content, marker)
        assert auth_target in block, marker
        assert "[mcp_host|127.0.0.1]:[mcp_port|8000]" not in block, marker

def test_remote_http_template_routes_same_application_topology_before_tls():
    content = _template("nginx-http-[site].conf")

    assert "location = /mcp {" in content
    assert "location = /query {" in content
    assert "location = / {" in content
    assert "location = /oauth/authorize {" in content
    assert "location = /oauth/token {" in content
    assert "location = /oauth/revoke {" in content
    assert "location = /settings/connections {" in content
    assert "proxy_pass http://[mcp_host|127.0.0.1]:[mcp_port|8000];" in content
    assert "proxy_pass http://[auth_host|127.0.0.1]:[auth_port|8001];" in content

def test_remote_templates_preserve_host_and_forwarded_request_context():
    for name in ("nginx-http-[site].conf", "nginx-https-[site].conf"):
        content = _template(name)

        assert "proxy_set_header Host $host;" in content
        assert "proxy_set_header X-Real-IP $remote_addr;" in content
        assert (
            "proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;"
            in content
        )
        assert "proxy_set_header X-Forwarded-Proto $scheme;" in content

def test_remote_templates_do_not_use_one_catch_all_application_upstream():
    for name in ("nginx-http-[site].conf", "nginx-https-[site].conf"):
        content = _template(name)

        assert "proxy_pass http://[host]:[port];" not in content
        assert "location / {\n        proxy_set_header" not in content

def test_remote_mcp_route_has_streaming_proxy_semantics():
    for name in ("nginx-http-[site].conf", "nginx-https-[site].conf"):
        content = _template(name)
        block = _block(content, "location = /mcp {")

        assert "proxy_http_version 1.1;" in block
        assert 'proxy_set_header Connection "";' in block
        assert "proxy_buffering off;" in block
        assert "proxy_request_buffering off;" in block
        assert "proxy_cache off;" in block
        assert "proxy_read_timeout [mcp_read_timeout|300s];" in block
        assert "proxy_send_timeout [mcp_send_timeout|300s];" in block

def test_remote_mcp_route_is_exact_and_does_not_strip_prefix():
    for name in ("nginx-http-[site].conf", "nginx-https-[site].conf"):
        content = _template(name)
        block = _block(content, "location = /mcp {")

        assert "location = /mcp {" in block
        assert "proxy_pass http://[mcp_host|127.0.0.1]:[mcp_port|8000];" in block
        assert "proxy_pass http://[mcp_host|127.0.0.1]:[mcp_port|8000]/;" not in block

def test_remote_auth_routes_do_not_inherit_mcp_streaming_policy():
    content = _template("nginx-https-[site].conf")

    for marker in (
        "location = / {",
        "location = /query {",
        "location = /oauth/authorize {",
        "location = /oauth/token {",
        "location = /oauth/revoke {",
        "location = /login {",
        "location = /connect {",
        "location = /consent {",
        "location = /settings/connections {",
    ):
        block = _block(content, marker)
        assert "proxy_buffering off;" not in block, marker
        assert "proxy_read_timeout" not in block, marker
        assert "proxy_send_timeout" not in block, marker

def test_remote_http_acme_challenge_is_filesystem_owned_not_proxied():
    content = _template("nginx-http-[site].conf")
    marker = "location ^~ /.well-known/acme-challenge/ {"
    block = _block(content, marker)

    assert "root [acme_webroot|/var/www/gway-acme];" in block
    assert "default_type text/plain;" in block
    assert "proxy_pass" not in block

def test_remote_https_redirect_server_preserves_acme_before_redirect():
    content = _template("nginx-https-[site].conf")
    first_server = content.split("\n}\n\nserver {", 1)[0]

    assert "location ^~ /.well-known/acme-challenge/ {" in first_server
    assert "root [acme_webroot|/var/www/gway-acme];" in first_server
    assert "return 301 https://$host$request_uri;" in first_server
    assert first_server.index("location ^~ /.well-known/acme-challenge/ {") < (
        first_server.index("location / {")
    )

def test_remote_well_known_oauth_routes_are_exact_and_distinct_from_acme():
    for name in ("nginx-http-[site].conf", "nginx-https-[site].conf"):
        content = _template(name)

        assert "location = /.well-known/oauth-protected-resource/mcp {" in content
        assert "location = /.well-known/oauth-authorization-server {" in content
        assert "location = /.well-known/gway-acceptance-client {" in content
        assert "location ^~ /.well-known/ {" not in content
        assert "location / .well-known" not in content

def test_remote_auth_surface_does_not_publish_unimplemented_prefixes():
    for name in ("nginx-http-[site].conf", "nginx-https-[site].conf"):
        content = _template(name)

        assert "location ^~ /oauth/ {" not in content
        assert "location ^~ /settings/ {" not in content
        for route in (
            "/oauth/authorize",
            "/oauth/token",
            "/oauth/revoke",
            "/settings/connections",
        ):
            assert f"location = {route} {{" in content

def test_remote_expose_package_has_deployment_recipes():
    root = remote_root()

    for name in (
        "expose.rx",
        "http.rx",
        "https.rx",
        "cleanup-http.rx",
        "actions-policy.rx",
        "nginx-http-[site].conf",
        "nginx-https-[site].conf",
    ):
        assert (root / name).is_file(), name

def test_remote_expose_composes_http_then_https_only():
    assert _commands("expose.rx") == ["./http.rx", "./https.rx"]

def test_remote_http_recipe_bootstraps_acme_and_remote_nginx_template():
    rendered = _commands("http.rx")

    assert rendered[:2] == [
        "ingest [nginx_executable|nginx] --kind proc --sudo",
        "ingest [mkdir_executable|mkdir] --kind proc --sudo",
    ]
    assert "mkdir -p [acme_webroot|/var/www/gway-acme]" in rendered
    assert any(
        command.startswith("render nginx-http-[site].conf") for command in rendered
    )
    assert any(command.startswith("link [nginx_available") for command in rendered)
    assert rendered[-3:] == ["nginx -t", "nginx -s reload", "commit remote-expose"]
    assert not any(command.startswith("certbot ") for command in rendered)

def test_remote_https_recipe_gets_certificate_before_tls_render():
    rendered = _commands("https.rx")

    assert rendered[:2] == [
        "ingest [nginx_executable|nginx] --kind proc --sudo",
        "ingest [certbot_executable|certbot] --kind proc --sudo",
    ]
    certbot = next(
        command for command in rendered if command.startswith("certbot certonly")
    )
    assert "--webroot" in certbot
    assert "--webroot-path [acme_webroot|/var/www/gway-acme]" in certbot
    assert "--domain [domain]" in certbot
    assert "--cert-name [domain]" in certbot
    assert "--email [email]" in certbot
    assert "--non-interactive" in certbot
    assert "--agree-tos" in certbot
    assert "--keep-until-expiring" in certbot

    render_index = next(
        index
        for index, command in enumerate(rendered)
        if command.startswith("render nginx-https-[site].conf")
    )
    assert rendered.index(certbot) < render_index
    assert rendered[-3:] == ["nginx -t", "nginx -s reload", "commit remote-expose"]

def test_remote_cleanup_removes_only_nginx_site_artifacts():
    rendered = _commands("cleanup-http.rx")

    assert rendered[0] == "ingest nginx --kind proc --sudo"
    assert rendered[1].startswith("remove [nginx_enabled")
    assert "--as root" in rendered[1]
    assert rendered[2].startswith("remove [nginx_available")
    assert "--as root" in rendered[2]
    assert rendered[3:6] == [
        "nginx -t",
        "nginx -s reload",
        "commit remote-cleanup",
    ]
    assert not any("certbot" in command for command in rendered)
    assert not any("letsencrypt" in command for command in rendered)
    assert not any("[acme_webroot" in command for command in rendered)

def test_remote_sampler_recipes_resolve_as_one_package(gateway):
    root = remote_root()

    for name in ("expose.rx", "http.rx", "https.rx", "cleanup-http.rx"):
        path = root / name
        assert recipe_path(gateway, path, allow_bare=False) == path

def test_remote_templates_resolve_from_remote_recipe_directory(
    gateway,
    tmp_path,
    monkeypatch,
):
    root = remote_root()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    gateway._recipe_stack = [root / "http.rx"]
    gateway.context["site"] = "remote-demo"
    try:
        renderer = gateway._renderer
        source, resolved = renderer.render.__globals__["_template_source"](
            gateway,
            "nginx-http-[site].conf",
        )
    finally:
        gateway.context.pop("site", None)
        gateway._recipe_stack = []

    assert source == root / "nginx-http-[site].conf"
    assert resolved == Path("nginx-http-remote-demo.conf")

def test_remote_http_mutations_share_transaction_before_validation():
    rendered = _commands("http.rx")
    render = next(
        command for command in rendered
        if command.startswith("render nginx-http-[site].conf")
    )
    link = next(
        command for command in rendered
        if command.startswith("link [nginx_available")
    )

    assert "--rollback remote-expose" in render
    assert "--rollback remote-expose" in link
    assert rendered.index(render) < rendered.index("nginx -t")
    assert rendered.index(link) < rendered.index("nginx -t")
    assert rendered.index("commit remote-expose") > rendered.index("nginx -s reload")

def test_remote_https_render_rolls_back_until_reload_succeeds():
    rendered = _commands("https.rx")
    render = next(
        command for command in rendered
        if command.startswith("render nginx-https-[site].conf")
    )

    assert "--rollback remote-expose" in render
    assert rendered.index(render) < rendered.index("nginx -t")
    assert rendered.index("commit remote-expose") > rendered.index("nginx -s reload")

def test_remote_cleanup_is_transactional_until_reload_succeeds():
    rendered = _commands("cleanup-http.rx")

    for command in rendered:
        if command.startswith("remove "):
            assert "--rollback remote-cleanup" in command

    assert rendered.index("commit remote-cleanup") > rendered.index("nginx -s reload")

def test_remote_exposure_uses_generic_journal_to_restore_failed_validation(
    gateway,
    tmp_path,
):
    template = tmp_path / "site.conf.tmpl"
    target = tmp_path / "site.conf"
    enabled = tmp_path / "site-enabled"

    template.write_text("new config", encoding="utf-8")
    target.write_text("old config", encoding="utf-8")

    with pytest.raises(RuntimeError, match="nginx validation failed"):
        with gateway.execution_scope():
            gateway.render(
                str(template),
                to=str(target),
                rollback="remote-expose",
            )
            gateway.link(
                str(target),
                to=str(enabled),
                rollback="remote-expose",
            )
            raise RuntimeError("nginx validation failed")

    assert target.read_text(encoding="utf-8") == "old config"
    assert not enabled.exists()
    assert gateway.journal.get("remote-expose") is None


def test_remote_https_public_contract_has_one_mcp_route_and_explicit_auth_routes():
    content = _template("nginx-https-[site].conf")
    mcp_target = "[mcp_host|127.0.0.1]:[mcp_port|8000]"
    auth_target = "[auth_host|127.0.0.1]:[auth_port|8001]"

    assert content.count("location = /mcp {") == 1
    assert _block(content, "location = /mcp {").count(mcp_target) == 1

    auth_routes = (
        "/",
        "/query",
        "/.well-known/oauth-protected-resource/mcp",
        "/.well-known/oauth-authorization-server",
        "/.well-known/gway-acceptance-client",
        "/oauth/authorize",
        "/oauth/token",
        "/oauth/revoke",
        "/login",
        "/connect",
        "/consent",
        "/settings/connections",
    )
    for route in auth_routes:
        marker = f"location = {route} {{"
        block = _block(content, marker)
        assert auth_target in block, route
        assert mcp_target not in block, route


def test_remote_https_contract_has_no_application_catch_all_proxy():
    content = _template("nginx-https-[site].conf")
    tls_server = content.split("\n}\n\nserver {", 1)[1]

    assert "location / {" not in tls_server
    assert "location ^~ /oauth/ {" not in tls_server
    assert "location ^~ /settings/ {" not in tls_server
    assert "location ^~ /.well-known/ {" not in tls_server


def test_remote_templates_default_both_application_upstreams_to_loopback():
    for name in ("nginx-http-[site].conf", "nginx-https-[site].conf"):
        content = _template(name)

        assert "[mcp_host|127.0.0.1]" in content
        assert "[auth_host|127.0.0.1]" in content
        assert "0.0.0.0" not in content



def test_remote_query_route_uses_auth_upstream_and_preserves_request_contract():
    auth_target = "[auth_host|127.0.0.1]:[auth_port|8001]"

    for name in ("nginx-http-[site].conf", "nginx-https-[site].conf"):
        content = _template(name)
        block = _block(content, "location = /query {")

        assert auth_target in block
        assert "[mcp_host|127.0.0.1]:[mcp_port|8000]" not in block
        assert "proxy_set_header Authorization $http_authorization;" in block
        assert "proxy_cache off;" in block
        assert 'add_header Cache-Control "no-store" always;' in block
        assert "proxy_pass http://[auth_host|127.0.0.1]:[auth_port|8001];" in block
        assert "proxy_pass http://[auth_host|127.0.0.1]:[auth_port|8001]/;" not in block


def test_remote_actions_routes_use_auth_upstream_and_preserve_contract():
    auth_target = "[auth_host|127.0.0.1]:[auth_port|8001]"
    mcp_target = "[mcp_host|127.0.0.1]:[mcp_port|8000]"

    for name in ("nginx-http-[site].conf", "nginx-https-[site].conf"):
        content = _template(name)

        openapi = _block(content, "location = /actions/openapi.json {")
        assert auth_target in openapi
        assert mcp_target not in openapi
        assert "proxy_buffering off;" not in openapi

        for route in ("/actions/query", "/actions/execute"):
            block = _block(content, f"location = {route} {{")
            assert auth_target in block
            assert mcp_target not in block
            assert "proxy_set_header Authorization $http_authorization;" in block
            assert "proxy_cache off;" in block
            assert 'add_header Cache-Control "no-store" always;' in block
            assert "proxy_buffering off;" not in block
            assert "proxy_read_timeout" not in block
            assert "proxy_send_timeout" not in block


def test_remote_actions_protected_resource_route_is_explicit():
    auth_target = "[auth_host|127.0.0.1]:[auth_port|8001]"

    for name in ("nginx-http-[site].conf", "nginx-https-[site].conf"):
        content = _template(name)
        marker = "location = /.well-known/oauth-protected-resource/actions {"
        block = _block(content, marker)

        assert marker in content
        assert auth_target in block
        assert "[mcp_host|127.0.0.1]:[mcp_port|8000]" not in block


def test_remote_public_contract_exposes_actions_without_catch_all():
    for name in ("nginx-http-[site].conf", "nginx-https-[site].conf"):
        content = _template(name)

        for route in (
            "/actions/openapi.json",
            "/actions/query",
            "/actions/execute",
            "/.well-known/oauth-protected-resource/actions",
        ):
            assert f"location = {route} {{" in content

        assert "location ^~ /actions/ {" not in content
        assert "location /actions/ {" not in content


def test_remote_actions_policy_is_exactly_limited_initial_scope():
    assert _commands("actions-policy.rx") == [
        "security scope set chatgpt-actions "
        "help log.sources log.read log.tail log.search"
    ]


def test_remote_actions_policy_does_not_grant_mutating_operations():
    command = _commands("actions-policy.rx")[0]

    assert "service" not in command
    assert "install" not in command
    assert "set env" not in command
    assert "security token" not in command
    assert "security oauth" not in command


def test_remote_privacy_route_is_explicit_and_uses_auth_upstream():
    auth_target = "[auth_host|127.0.0.1]:[auth_port|8001]"

    for name in ("nginx-http-[site].conf", "nginx-https-[site].conf"):
        content = _template(name)
        marker = "location = /privacy {"
        block = _block(content, marker)

        assert marker in content
        assert auth_target in block
        assert "[mcp_host|127.0.0.1]:[mcp_port|8000]" not in block
