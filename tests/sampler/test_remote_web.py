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
        "location ^~ /oauth/ {",
        "location = /login {",
        "location = /connect {",
        "location = /consent {",
        "location ^~ /settings/ {",
    ):
        block = _block(content, marker)
        assert auth_target in block, marker
        assert "[mcp_host|127.0.0.1]:[mcp_port|8000]" not in block, marker


def test_remote_http_template_routes_same_application_topology_before_tls():
    content = _template("nginx-http-[site].conf")

    assert "location = /mcp {" in content
    assert "location = / {" in content
    assert "location ^~ /oauth/ {" in content
    assert "location ^~ /settings/ {" in content
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
