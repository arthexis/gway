from pathlib import Path

from gway.recipes import load_recipe, recipe_path


def sampler_root():
    return Path(__file__).resolve().parents[2] / "sampler" / "web" / "expose"


def rendered_commands(path):
    commands, _ = load_recipe(path)
    return [" ".join(str(token) for token in command["tokens"]) for command in commands]


def test_web_expose_sampler_is_not_builtin(gateway):
    assert gateway.ops.resolve("expose") is None
    assert gateway.ops.resolve("web expose") is None


def test_web_expose_package_has_required_shape():
    root = sampler_root()

    assert (root / "expose.rx").is_file()
    assert (root / "dns-http.rx").is_file()
    assert (root / "http.rx").is_file()
    assert (root / "https.rx").is_file()
    assert (root / "cleanup.rx").is_file()
    assert (root / "godaddy-setup.rx").is_file()
    assert (root / "nginx-http-[name].conf").is_file()
    assert (root / "nginx-https-[name].conf").is_file()


def test_web_expose_default_composes_http_then_https():
    assert rendered_commands(sampler_root() / "expose.rx") == ["./http", "./https"]


def test_web_expose_http_bootstraps_acme_and_nginx():
    rendered = rendered_commands(sampler_root() / "http.rx")

    assert rendered[:2] == [
        "ingest nginx --kind proc --sudo",
        "ingest mkdir --kind proc --sudo",
    ]
    assert "mkdir -p [acme_webroot|/var/www/gway-acme]" in rendered
    assert any(
        command.startswith("render nginx-http-[name].conf") for command in rendered
    )
    assert any(command.startswith("link [nginx_available") for command in rendered)
    assert rendered[-2:] == ["nginx -t", "nginx -s reload"]
    assert not any(command.startswith("certbot ") for command in rendered)


def test_web_expose_https_uses_certbot_webroot_before_tls_render():
    rendered = rendered_commands(sampler_root() / "https.rx")

    assert rendered[:2] == [
        "ingest nginx --kind proc --sudo",
        "ingest certbot --kind proc --sudo",
    ]
    certbot = next(
        command for command in rendered if command.startswith("certbot certonly")
    )
    assert "--webroot" in certbot
    assert "--webroot-path [acme_webroot|/var/www/gway-acme]" in certbot
    assert "--domain" in certbot
    assert "--email" in certbot
    assert "--cert-name [domain]" in certbot
    assert "--agree-tos" in certbot
    assert "--non-interactive" in certbot
    assert not any(command.startswith("dns ") for command in rendered)

    render_index = next(
        index
        for index, command in enumerate(rendered)
        if command.startswith("render nginx-https-[name].conf")
    )
    certbot_index = rendered.index(certbot)
    assert certbot_index < render_index
    assert rendered[-2:] == ["nginx -t", "nginx -s reload"]


def test_web_expose_http_template_matches_certbot_webroot():
    content = (sampler_root() / "nginx-http-[name].conf").read_text(encoding="utf-8")

    assert "listen 80;" in content
    assert "server_name [domain];" in content
    assert "location ^~ /.well-known/acme-challenge/" in content
    assert "root [acme_webroot|/var/www/gway-acme];" in content
    assert "proxy_pass http://[host|127.0.0.1]:[port|8000];" in content
    assert "listen 443 ssl;" not in content


def test_web_expose_https_template_serves_tls_and_preserves_acme():
    content = (sampler_root() / "nginx-https-[name].conf").read_text(encoding="utf-8")

    assert "listen 80;" in content
    assert "location ^~ /.well-known/acme-challenge/" in content
    assert "return 301 https://$host$request_uri;" in content
    assert "listen 443 ssl;" in content
    assert "ssl_certificate /etc/letsencrypt/live/[domain]/fullchain.pem;" in content
    assert "ssl_certificate_key /etc/letsencrypt/live/[domain]/privkey.pem;" in content
    assert "proxy_pass http://[host|127.0.0.1]:[port|8000];" in content


def test_sampler_package_resolves_default_and_children(gateway):
    root = sampler_root()

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
    gateway, tmp_path, monkeypatch
):
    root = sampler_root()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    gateway._recipe_stack = [root / "http.rx"]
    gateway.context["name"] = "demo"
    try:
        renderer = gateway._renderer
        source, resolved = renderer.render.__globals__["_template_source"](
            gateway,
            "nginx-http-[name].conf",
        )
    finally:
        gateway.context.pop("name", None)
        gateway._recipe_stack = []

    assert source == root / "nginx-http-[name].conf"
    assert resolved == Path("nginx-http-demo.conf")


def test_web_expose_dns_http_is_explicit_provider_neutral_preparation():
    rendered = rendered_commands(sampler_root() / "dns-http.rx")

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

    assert rendered[2].startswith("repeat")
    assert "--until true" in rendered[2]
    assert "--interval 10" in rendered[2]
    assert "--max 60" in rendered[2]


def test_web_expose_default_does_not_mutate_dns():
    rendered = rendered_commands(sampler_root() / "expose.rx")

    assert rendered == ["./http", "./https"]
    assert "./dns-http" not in rendered


def test_web_expose_cleanup_removes_only_sampler_artifacts():
    rendered = rendered_commands(sampler_root() / "cleanup.rx")

    assert rendered[0] == "./cleanup-http"

    dns_delete = rendered[1]
    assert dns_delete.startswith("dns delete [domain]")
    assert "--type A" in dns_delete
    assert "--value [public_ipv4]" in dns_delete
    assert "--backend [dns_backend|godaddy]" in dns_delete
    assert "--zone [zone]" in dns_delete

    http_cleanup = rendered_commands(sampler_root() / "cleanup-http.rx")
    assert http_cleanup[0] == "ingest nginx --kind proc --sudo"
    assert http_cleanup[1].startswith("remove [nginx_enabled")
    assert "--as root" in http_cleanup[1]
    assert http_cleanup[2].startswith("remove [nginx_available")
    assert "--as root" in http_cleanup[2]
    assert http_cleanup[3:5] == ["nginx -t", "nginx -s reload"]


def test_web_expose_cleanup_does_not_remove_certificates_or_shared_webroot():
    rendered = rendered_commands(sampler_root() / "cleanup.rx")

    assert not any("certbot" in command for command in rendered)
    assert not any("letsencrypt" in command for command in rendered)
    assert not any("[acme_webroot" in command for command in rendered)


def test_godaddy_setup_uses_generic_input_and_secret_store():
    rendered = rendered_commands(sampler_root() / "godaddy-setup.rx")

    assert rendered == [
        "input GoDaddy key --as godaddy_key --secret",
        "input GoDaddy secret --as godaddy_secret --secret",
        "secret write dns godaddy key [godaddy_key]",
        "secret write dns godaddy secret [godaddy_secret]",
    ]
