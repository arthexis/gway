import json
from urllib.error import HTTPError

import pytest

from gway import Gateway


class Response:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return b""


def test_dns_operations_are_registered():
    gateway = Gateway()

    assert gateway.ops.resolve("dns.create") is not None
    assert gateway.ops.resolve("dns.ready") is not None
    assert gateway.ops.resolve("dns.delete") is not None


def test_dns_create_uses_proven_godaddy_v1_replace_shape(monkeypatch):
    gateway = Gateway()
    observed = {}

    monkeypatch.setenv("GODADDY_API_KEY", "key")
    monkeypatch.setenv("GODADDY_API_SECRET", "secret")

    def open_(request, timeout):
        observed["url"] = request.full_url
        observed["method"] = request.get_method()
        observed["authorization"] = request.headers["Authorization"]
        observed["payload"] = json.loads(request.data.decode("utf-8"))
        observed["timeout"] = timeout
        return Response()

    monkeypatch.setattr("gway.dns.urlopen", open_)

    result = gateway(
        "dns create remote.arthexis.com "
        "--type A --value 192.0.2.10 --backend godaddy --zone arthexis.com"
    )

    assert observed == {
        "url": "https://api.godaddy.com/v1/domains/arthexis.com/records/A/remote",
        "method": "PUT",
        "authorization": "sso-key key:secret",
        "payload": [{"data": "192.0.2.10", "ttl": 600}],
        "timeout": 30,
    }
    assert result["domain"] == "remote.arthexis.com"
    assert result["value"] == "192.0.2.10"


def test_dns_create_prefers_godaddy_pat(monkeypatch):
    gateway = Gateway()
    observed = {}

    monkeypatch.setenv("GODADDY_PAT", "token")
    monkeypatch.delenv("GODADDY_API_KEY", raising=False)
    monkeypatch.delenv("GODADDY_API_SECRET", raising=False)

    def open_(request, timeout):
        observed["authorization"] = request.headers["Authorization"]
        return Response()

    monkeypatch.setattr("gway.dns.urlopen", open_)

    gateway(
        "dns create remote.arthexis.com "
        "--type A --value 192.0.2.10 --zone arthexis.com"
    )

    assert observed["authorization"] == "Bearer token"


def test_dns_create_reports_missing_credentials_without_values(monkeypatch):
    gateway = Gateway()
    monkeypatch.delenv("GODADDY_PAT", raising=False)
    monkeypatch.delenv("GODADDY_API_KEY", raising=False)
    monkeypatch.delenv("GODADDY_API_SECRET", raising=False)

    with pytest.raises(RuntimeError, match="GODADDY_API_KEY"):
        gateway(
            "dns create remote.arthexis.com "
            "--type A --value 192.0.2.10 --zone arthexis.com"
        )


def test_dns_create_surfaces_provider_error_without_secret(monkeypatch):
    gateway = Gateway()
    monkeypatch.setenv("GODADDY_API_KEY", "key")
    monkeypatch.setenv("GODADDY_API_SECRET", "secret")

    def open_(request, timeout):
        from io import BytesIO

        raise HTTPError(
            request.full_url,
            403,
            "Forbidden",
            {},
            BytesIO(b'{"message":"denied"}'),
        )

    monkeypatch.setattr("gway.dns.urlopen", open_)

    with pytest.raises(RuntimeError, match="HTTP 403: denied"):
        gateway(
            "dns create remote.arthexis.com "
            "--type A --value 192.0.2.10 --zone arthexis.com"
        )


def test_dns_ready_checks_public_a_record(monkeypatch):
    gateway = Gateway()

    monkeypatch.setattr(
        "gway.dns.socket.getaddrinfo",
        lambda *args, **kwargs: [
            (2, 1, 6, "", ("192.0.2.10", 0)),
            (2, 1, 6, "", ("192.0.2.11", 0)),
        ],
    )

    assert gateway(
        "dns ready remote.arthexis.com "
        "--type A --value 192.0.2.10 --zone arthexis.com"
    ) is True


def test_dns_delete_uses_name_and_type(monkeypatch):
    gateway = Gateway()
    observed = {}

    monkeypatch.setenv("GODADDY_API_KEY", "key")
    monkeypatch.setenv("GODADDY_API_SECRET", "secret")

    def open_(request, timeout):
        observed["url"] = request.full_url
        observed["method"] = request.get_method()
        return Response()

    monkeypatch.setattr("gway.dns.urlopen", open_)

    gateway(
        "dns delete remote.arthexis.com "
        "--type A --value 192.0.2.10 --zone arthexis.com"
    )

    assert observed == {
        "url": "https://api.godaddy.com/v1/domains/arthexis.com/records/A/remote",
        "method": "DELETE",
    }
