from pathlib import Path

from gway.environment import BACKEND_ENVIRONMENT, TRANSITIONAL_SEMANTIC_ENVIRONMENT


ROOT = Path(__file__).resolve().parents[2]


def test_dns_module_has_no_physical_credential_knowledge():
    text = (ROOT / "gway" / "dns.py").read_text(encoding="utf-8")

    forbidden = (
        "GODADDY_PAT",
        "GODADDY_API_KEY",
        "GODADDY_API_SECRET",
        "GWAY_SECRETS_DIR",
        "/etc/gway/secrets",
        "process_environment",
        "environment_value",
    )

    assert [value for value in forbidden if value in text] == []


def test_dns_credential_environment_left_transitional_inventory():
    assert "GODADDY_PAT" not in TRANSITIONAL_SEMANTIC_ENVIRONMENT
    assert "GODADDY_API_KEY" not in TRANSITIONAL_SEMANTIC_ENVIRONMENT
    assert "GODADDY_API_SECRET" not in TRANSITIONAL_SEMANTIC_ENVIRONMENT


def test_secrets_root_environment_is_backend_configuration():
    assert "GWAY_SECRETS_DIR" in BACKEND_ENVIRONMENT
    assert "GWAY_SECRETS_DIR" not in TRANSITIONAL_SEMANTIC_ENVIRONMENT
