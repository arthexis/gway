import re
import shutil
import subprocess
from pathlib import Path

import pytest


NGINX_TEMPLATES = (
    "bootstrap/nginx-http-[site].conf",
    "bootstrap/nginx-https-[site].conf",
    "web/expose/nginx-http-[site].conf",
    "web/expose/nginx-https-[site].conf",
    "web/remote/nginx-http-[site].conf",
    "web/remote/nginx-https-[site].conf",
)

_SIGIL = re.compile(r"\[([A-Za-z_][A-Za-z0-9_]*)(?:\|([^\]]*))?\]")


def _render_nginx_template(source: str, tmp_path: Path) -> str:
    values = {
        "domain": "example.test",
        "site": "example_test",
        "site_key": "example_test",
        "acme_webroot": str(tmp_path / "acme"),
        "root": str(tmp_path / "www"),
        "headers": "",
        "response_headers": "",
        "host": "127.0.0.1",
        "port": "8080",
    }

    def replace(match: re.Match[str]) -> str:
        name, fallback = match.groups()
        if name in values:
            return values[name]
        if fallback is not None:
            return fallback
        raise AssertionError(f"missing nginx template fixture for [{name}]")

    rendered = _SIGIL.sub(replace, source)
    rendered = rendered.replace("[[", "[").replace("]]", "]")
    return (
        rendered
        .replace("listen 80;", "listen 18080;")
        .replace("listen [::]:80;", "listen [::]:18080;")
        .replace("listen 443 ssl;", "listen 18443 ssl;")
        .replace("listen [::]:443 ssl;", "listen [::]:18443 ssl;")
    )


@pytest.mark.parametrize("template", NGINX_TEMPLATES)
def test_nginx_templates_parse_with_real_nginx(sampler_path, tmp_path, template):
    nginx = shutil.which("nginx")
    openssl = shutil.which("openssl")
    if nginx is None or openssl is None:
        pytest.skip("real nginx template validation requires nginx and openssl")

    source = sampler_path(template).read_text(encoding="utf-8")
    rendered = _render_nginx_template(source, tmp_path)

    cert = tmp_path / "fullchain.pem"
    key = tmp_path / "privkey.pem"
    subprocess.run(
        [
            openssl,
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-subj",
            "/CN=example.test",
            "-keyout",
            str(key),
            "-out",
            str(cert),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    rendered = rendered.replace(
        "/etc/letsencrypt/live/example.test/fullchain.pem",
        str(cert),
    ).replace(
        "/etc/letsencrypt/live/example.test/privkey.pem",
        str(key),
    )

    candidate = tmp_path / "candidate.conf"
    candidate.write_text(rendered, encoding="utf-8")
    (tmp_path / "acme").mkdir()
    (tmp_path / "www").mkdir()

    nginx_conf = tmp_path / "nginx.conf"
    nginx_conf.write_text(
        "\n".join(
            (
                "worker_processes 1;",
                f"error_log {tmp_path / 'error.log'};",
                f"pid {tmp_path / 'nginx.pid'};",
                "events { worker_connections 16; }",
                "http {",
                "    access_log off;",
                f"    include {candidate};",
                "}",
                "",
            )
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [nginx, "-t", "-c", str(nginx_conf), "-p", str(tmp_path)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
