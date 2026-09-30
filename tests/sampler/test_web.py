from pathlib import Path

from gway.publication import publish
from gway.recipe import recipe_path

def test_web_expose_sampler_is_not_builtin(gateway):
    assert gateway.ops.resolve("expose") is None
    assert gateway.ops.resolve("web expose") is None


def test_web_expose_package_has_required_shape(sampler_path):
    root = sampler_path("web/expose")

    assert (root / "expose.rx").is_file()
    assert (root / "dns-http.rx").is_file()
    assert (root / "http.rx").is_file()
    assert (root / "https.rx").is_file()
    assert (root / "cleanup.rx").is_file()
    assert (root / "nginx-http-[site].conf").is_file()
    assert (root / "nginx-https-[site].conf").is_file()


def test_web_expose_default_composes_http_then_https(recipe_commands):
    assert recipe_commands("web/expose/expose.rx") == ["./http.rx", "./https.rx"]


def test_web_expose_http_bootstraps_acme_and_nginx(recipe_commands):
    rendered = recipe_commands("web/expose/http.rx")

    assert rendered[:3] == [
        "expose normalize site key [site]",
        "ingest [nginx_executable|nginx] --kind proc --sudo",
        "ingest [mkdir_executable|mkdir] --kind proc --sudo",
    ]
    assert "mkdir -p [acme_webroot|/var/www/gway-acme]" in rendered
    assert any(
        command.startswith("render nginx-http-[site].conf") for command in rendered
    )
    assert any(command.startswith("link [nginx_available") for command in rendered)
    assert rendered[-2:] == ["nginx -t", "nginx -s reload"]
    assert not any(command.startswith("certbot ") for command in rendered)


def test_web_expose_https_uses_certbot_webroot_before_tls_render(recipe_commands):
    rendered = recipe_commands("web/expose/https.rx")

    assert rendered[:3] == [
        "expose normalize site key [site]",
        "ingest [nginx_executable|nginx] --kind proc --sudo",
        "ingest [certbot_executable|certbot] --kind proc --sudo",
    ]
    certbot = next(
        command for command in rendered if command.startswith("certbot certonly")
    )
    assert "--webroot" in certbot
    assert "--webroot-path [acme_webroot|/var/www/gway-acme]" in certbot
    assert "--domain [domain]" in certbot
    assert "--email [email]" in certbot
    assert "--cert-name [domain]" in certbot
    assert "--agree-tos" in certbot
    assert "--non-interactive" in certbot
    assert "--keep-until-expiring" in certbot
    assert not any(command.startswith("dns ") for command in rendered)

    render_index = next(
        index
        for index, command in enumerate(rendered)
        if command.startswith("render nginx-https-[site].conf")
    )
    certbot_index = rendered.index(certbot)
    assert certbot_index < render_index
    assert rendered[-2:] == ["nginx -t", "nginx -s reload"]


def test_web_expose_http_template_matches_certbot_webroot(sampler_path):
    content = (sampler_path("web/expose") / "nginx-http-[site].conf").read_text(encoding="utf-8")

    assert "listen 80;" in content
    assert "listen [[::]]:80;" in content
    assert "server_name [domain];" in content
    assert "location ^~ /.well-known/acme-challenge/" in content
    assert "root [acme_webroot|/var/www/gway-acme];" in content
    assert "return 301 https://[domain]$request_uri;" in content
    assert "proxy_pass http://[host]:[port];" not in content
    assert "listen 443 ssl;" not in content


def test_web_expose_https_template_serves_tls_and_preserves_acme(sampler_path):
    content = (sampler_path("web/expose") / "nginx-https-[site].conf").read_text(encoding="utf-8")

    assert "listen 80;" in content
    assert "location ^~ /.well-known/acme-challenge/" in content
    assert "return 301 https://[domain]$request_uri;" in content
    assert "listen 443 ssl;" in content
    assert "listen [[::]]:443 ssl;" in content
    assert "ssl_certificate /etc/letsencrypt/live/[domain]/fullchain.pem;" in content
    assert "ssl_certificate_key /etc/letsencrypt/live/[domain]/privkey.pem;" in content
    assert "proxy_pass http://[host]:[port];" in content


def test_sampler_package_resolves_default_and_children(sampler_path, gateway):
    root = sampler_path("web/expose")

    assert recipe_path(gateway, root / "expose.rx", allow_bare=False) == (
        root / "expose.rx"
    )
    assert recipe_path(gateway, root / "http.rx", allow_bare=False) == (
        root / "http.rx"
    )
    assert recipe_path(gateway, root / "https.rx", allow_bare=False) == (
        root / "https.rx"
    )
    assert recipe_path(gateway, root / "cleanup.rx", allow_bare=False) == (
        root / "cleanup.rx"
    )


def test_sampler_templates_resolve_from_recipe_directory(
    sampler_path, gateway, tmp_path, monkeypatch
):
    root = sampler_path("web/expose")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    gateway._recipe_stack = [root / "http.rx"]
    gateway.context["site"] = "demo"
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
    assert resolved == Path("nginx-http-demo.conf")


def test_web_expose_dns_http_is_explicit_provider_neutral_preparation(recipe_commands):
    rendered = recipe_commands("web/expose/dns-http.rx")

    assert rendered[0].startswith("dns create [domain]")
    assert "--type A" in rendered[0]
    assert "--value [public_ipv4]" in rendered[0]
    assert "--backend [dns_backend|godaddy]" in rendered[0]
    assert "--zone [zone]" in rendered[0]

    assert rendered[1].startswith("dns ready [domain]")
    assert "--type A" in rendered[1]
    assert "--value [public_ipv4]" in rendered[1]
    assert "--backend [dns_backend|godaddy]" in rendered[1]
    assert "--zone [zone]" in rendered[1]
    assert " - repeat " in rendered[1]
    assert "--until true" in rendered[1]
    assert "--interval 10" in rendered[1]
    assert "--max 60" in rendered[1]
    assert len(rendered) == 2


def test_web_expose_default_does_not_mutate_dns(recipe_commands):
    rendered = recipe_commands("web/expose/expose.rx")

    assert rendered == ["./http.rx", "./https.rx"]
    assert "./dns-http" not in rendered


def test_web_expose_cleanup_removes_only_sampler_artifacts(recipe_commands):
    rendered = recipe_commands("web/expose/cleanup.rx")

    assert rendered[0] == "./cleanup-http"

    dns_delete = rendered[1]
    assert dns_delete.startswith("dns delete [domain]")
    assert "--type A" in dns_delete
    assert "--value [public_ipv4]" in dns_delete
    assert "--backend [dns_backend|godaddy]" in dns_delete
    assert "--zone [zone]" in dns_delete

    http_cleanup = recipe_commands("web/expose/cleanup-http.rx")
    assert http_cleanup[0] == "ingest nginx --kind proc --sudo"
    assert http_cleanup[1].startswith("remove [nginx_enabled")
    assert "--as root" in http_cleanup[1]
    assert http_cleanup[2].startswith("remove [nginx_available")
    assert "--as root" in http_cleanup[2]
    assert http_cleanup[3:5] == ["nginx -t", "nginx -s reload"]


def test_web_expose_cleanup_does_not_remove_certificates_or_shared_webroot(recipe_commands):
    rendered = recipe_commands("web/expose/cleanup.rx")

    assert not any("certbot" in command for command in rendered)
    assert not any("letsencrypt" in command for command in rendered)
    assert not any("[acme_webroot" in command for command in rendered)


def test_web_expose_templates_reject_unknown_or_missing_hosts(sampler_path):
    for name in ("nginx-http-[site].conf", "nginx-https-[site].conf"):
        content = (sampler_path("web/expose") / name).read_text(encoding="utf-8")

        assert 'if ($http_host = "") {' in content
        assert "if ($host != [domain]) {" in content
        assert content.count("return 444;") >= 2


def test_web_expose_https_template_sets_safe_edge_defaults(sampler_path):
    content = (sampler_path("web/expose") / "nginx-https-[site].conf").read_text(encoding="utf-8")

    assert "server_tokens off;" in content
    assert "ssl_protocols TLSv1.2 TLSv1.3;" in content
    assert 'add_header Strict-Transport-Security "max-age=31536000" always;' in content
    assert 'add_header X-Content-Type-Options "nosniff" always;' in content
    assert 'add_header Referrer-Policy "same-origin" always;' in content
    assert "[response_headers|]" in content
    tls_server = content.rsplit("server {", 1)[1]
    location = tls_server.split("    location / {", 1)[1]
    assert "add_header" not in location


def test_web_expose_https_rejects_common_scanner_paths_at_edge(sampler_path):
    content = (
        sampler_path("web/expose") / "nginx-https-[site].conf"
    ).read_text(encoding="utf-8")

    assert r"location ~* \.php(?:/|$) {" in content
    assert "wp-admin|wp-content|wp-includes|wordpress" in content
    assert r"location ~* ^/(?:\.env|\.git)(?:/|$) {" in content
    assert content.count("return 404;") >= 6


def test_web_expose_https_serves_robots_without_waking_application(sampler_path):
    content = (
        sampler_path("web/expose") / "nginx-https-[site].conf"
    ).read_text(encoding="utf-8")

    block = content.split("location = /robots.txt {", 1)[1].split("}", 1)[0]
    assert "default_type text/plain;" in block
    assert 'return 200 "User-agent: *\\nDisallow:\\n";' in block
    assert "proxy_pass" not in block


def test_web_expose_rate_limits_only_selected_auth_paths(sampler_path):
    content = (
        sampler_path("web/expose") / "nginx-https-[site].conf"
    ).read_text(encoding="utf-8")

    assert "map $uri $gway_expose_auth_key_[site_key] {" in content
    assert 'default "";' in content
    assert "admin(?:/|$)|login/?$|accounts/login/?$" in content
    assert (
        "limit_req_zone $gway_expose_auth_key_[site_key] "
        "zone=gway_expose_auth_[site_key]:10m rate=5r/s;"
    ) in content
    assert "limit_req zone=gway_expose_auth_[site_key] burst=20 nodelay;" in content
    assert "limit_req_status 429;" in content


def test_web_expose_adds_bounded_client_and_upstream_timeouts(sampler_path):
    content = (
        sampler_path("web/expose") / "nginx-https-[site].conf"
    ).read_text(encoding="utf-8")

    assert "client_header_timeout 15s;" in content
    assert "client_body_timeout 30s;" in content
    assert "proxy_connect_timeout 10s;" in content


def test_web_expose_normalizes_site_for_nginx_identifiers(sampler_path):
    import runpy

    namespace = runpy.run_path(str(sampler_path("web/expose/expose.py")))
    normalize_site_key = namespace["normalize_site_key"]

    assert normalize_site_key("arthexis.com") == {"site_key": "arthexis_com"}
    assert normalize_site_key("my-site") == {"site_key": "my_site"}
    assert normalize_site_key("9site") == {"site_key": "_9site"}
    assert normalize_site_key("site_name") == {"site_key": "site_name"}


def test_web_expose_normalize_site_publishes_site_key_to_context(
    sampler_path, gateway
):
    import runpy

    namespace = runpy.run_path(str(sampler_path("web/expose/expose.py")))
    result = namespace["normalize_site_key"]("register-arthexis-com")

    gateway.context["site"] = "register-arthexis-com"
    publish(gateway, "key", result)

    assert result == {"site_key": "register_arthexis_com"}
    assert gateway.context["site_key"] == "register_arthexis_com"
    assert gateway.context["site"] == "register-arthexis-com"
    assert gateway.results["key"] is result


def test_web_expose_rate_limit_identifiers_use_normalized_site_key(sampler_path):
    content = (
        sampler_path("web/expose") / "nginx-https-[site].conf"
    ).read_text(encoding="utf-8")

    assert "$gway_expose_auth_key_[site_key]" in content
    assert "zone=gway_expose_auth_[site_key]:10m" in content
    assert "$gway_expose_auth_key_[site]" not in content
