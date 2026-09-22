from pathlib import Path


def remote_root():
    return Path(__file__).resolve().parents[2] / "sampler" / "web" / "remote"


def _template(name):
    return (remote_root() / name).read_text(encoding="utf-8")


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
        "location = /.well-known/oauth-protected-resource/mcp {",
        "location = /.well-known/oauth-authorization-server {",
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
