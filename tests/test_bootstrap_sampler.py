from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = ROOT / "sampler" / "bootstrap"


def test_gway_bootstrap_installs_only_released_package():
    script = (BOOTSTRAP / "gway.sh").read_text(encoding="utf-8")

    assert script.startswith("#!/bin/sh\n# GWAY_BOOTSTRAP_V1\n")
    assert "uv/install.sh" in script
    assert 'tool install --upgrade gway' in script
    assert "git+https://github.com/arthexis/gway" not in script
    assert '"$GWAY" version' in script


def test_watchtower_bootstrap_recipe_owns_dns_tls_and_static_site():
    recipe = (BOOTSTRAP / "watchtower.rx").read_text(encoding="utf-8")

    assert "install.arthexis.com" in recipe
    assert "dns create [domain]" in recipe
    assert "dns ready [domain]" in recipe
    assert "render gway.sh" in recipe
    assert "certbot certonly" in recipe
    assert "nginx-https-[site].conf" in recipe
    assert "commit gway-bootstrap" in recipe


def test_bootstrap_https_site_only_serves_exact_gway_path():
    nginx = (BOOTSTRAP / "nginx-https-[site].conf").read_text(encoding="utf-8")

    assert "location = /gway" in nginx
    assert "Cache-Control \"no-store\"" in nginx
    assert "location / {" in nginx
    assert "return 404;" in nginx
