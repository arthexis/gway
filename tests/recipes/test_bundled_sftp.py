from gway.bundled import resolve
from gway.recipes import load_recipe


def _text(name):
    return resolve(name).read_text(encoding="utf-8")


def test_bundled_sftp_contract_resolves_all_lifecycle_recipes():
    setup = resolve("sftp/setup")
    expose = resolve("sftp/expose")
    cleanup = resolve("sftp/cleanup")

    assert setup.name == "setup.rx"
    assert expose.name == "expose.rx"
    assert cleanup.name == "cleanup.rx"
    assert setup.parent == expose.parent == cleanup.parent


def test_sftp_s1_contracts_are_declarative_skeletons():
    for name in ("sftp/setup", "sftp/expose", "sftp/cleanup"):
        commands, comments = load_recipe(resolve(name))
        assert commands == []
        assert comments


def test_sftp_setup_contract_documents_host_defaults():
    content = _text("sftp/setup")

    assert "--name" in content and "default: sftp" in content
    assert "--root" in content and "default: /srv/gway-sftp" in content
    assert "--user" in content and "default: gway-sftp" in content
    assert "--group" in content and "default: gway-sftp" in content
    assert "--port" in content and "default: 22" in content
    assert "--destination" in content
    assert "--domain" not in content


def test_sftp_expose_contract_is_dns_only_and_provider_neutral():
    content = _text("sftp/expose")
    lowered = content.casefold()

    assert "--domain" in content
    assert "--zone" in content
    assert "--public-ipv4" in content
    assert "--dns-backend" in content
    assert "default: godaddy" in lowered
    assert "--port" in content and "default: 22" in content
    assert "nginx" not in lowered
    assert "certbot" not in lowered
    assert "http" not in lowered
    assert "acme" not in lowered


def test_sftp_cleanup_preserves_data_and_dns_by_default():
    content = _text("sftp/cleanup").casefold()

    assert "--preserve-data" in content
    assert "default: true" in content
    assert "--remove-dns" in content
    assert "default: false" in content


def test_sftp_contract_stays_generic():
    content = "\n".join(
        _text(name)
        for name in ("sftp/setup", "sftp/expose", "sftp/cleanup")
    )

    assert "backups.arthexis.com" not in content
    assert "arthexis.com" not in content
    assert "002" not in content
    assert "005" not in content
