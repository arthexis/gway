"""Provider-neutral DNS operations used by deployment recipes."""

from __future__ import annotations

import json
import os
import socket
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


class Controller:
    """DNS lifecycle facade with provider-specific backends."""

    def __init__(self, gateway):
        self.gateway = gateway

    @staticmethod
    def _backend(name):
        value = str(name or "godaddy").strip().lower()
        if value != "godaddy":
            raise ValueError(f"Unsupported DNS backend: {name}")
        return value

    @staticmethod
    def _zone(domain, zone):
        domain = str(domain).strip().rstrip(".")
        zone = str(zone or domain).strip().rstrip(".")
        if not domain or not zone:
            raise ValueError("DNS domain and zone must be non-empty")
        if domain != zone and not domain.endswith("." + zone):
            raise ValueError(f"DNS domain {domain!r} is outside zone {zone!r}")
        return domain, zone

    @staticmethod
    def _record_name(domain, zone):
        if domain == zone:
            return "@"
        return domain[: -(len(zone) + 1)]

    @staticmethod
    def _auth_header():
        pat = os.environ.get("GODADDY_PAT", "").strip()
        if pat:
            return f"Bearer {pat}"
        key = os.environ.get("GODADDY_API_KEY", "").strip()
        secret = os.environ.get("GODADDY_API_SECRET", "").strip()
        missing = []
        if not key:
            missing.append("GODADDY_API_KEY")
        if not secret:
            missing.append("GODADDY_API_SECRET")
        if missing:
            raise RuntimeError(
                "GoDaddy DNS credentials are not configured: "
                + ", ".join(missing)
                + " (or set GODADDY_PAT)"
            )
        return f"sso-key {key}:{secret}"

    @staticmethod
    def _request(method, url, *, payload=None):
        data = None
        headers = {
            "Authorization": Controller._auth_header(),
            "Accept": "application/json",
        }
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(url, data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=30) as response:
                body = response.read()
                return response.status, body
        except HTTPError as error:
            body = error.read().decode("utf-8", "replace")
            detail = body[:500]
            try:
                payload = json.loads(body)
            except ValueError:
                payload = None
            if isinstance(payload, dict):
                detail = str(
                    payload.get("message")
                    or payload.get("detail")
                    or payload.get("error")
                    or detail
                )
            raise RuntimeError(
                f"GoDaddy DNS API {method} failed with HTTP {error.code}: {detail}"
            ) from error
        except URLError as error:
            raise RuntimeError(f"GoDaddy DNS API request failed: {error.reason}") from error

    def create(
        self,
        domain,
        *,
        type="A",
        value,
        backend="godaddy",
        zone=None,
        ttl=600,
    ):
        """Create or replace one DNS record.

        Args:
            domain: Fully-qualified record name.
            type: DNS record type. Defaults to A.
            value: DNS record value.
            backend: DNS provider backend. Defaults to godaddy.
            zone: Authoritative DNS zone. Defaults to domain.
            ttl: Record TTL in seconds. Defaults to 600.
        """
        self._backend(backend)
        domain, zone = self._zone(domain, zone)
        record_type = str(type).upper()
        name = self._record_name(domain, zone)
        url = (
            "https://api.godaddy.com/v1/domains/"
            f"{quote(zone, safe='')}/records/{quote(record_type, safe='')}/"
            f"{quote(name, safe='@._-')}"
        )
        payload = [{"data": str(value), "ttl": int(ttl)}]
        self._request("PUT", url, payload=payload)
        return {
            "domain": domain,
            "zone": zone,
            "type": record_type,
            "value": str(value),
            "backend": "godaddy",
        }

    def ready(
        self,
        domain,
        *,
        type="A",
        value,
        backend="godaddy",
        zone=None,
    ):
        """Return whether public DNS resolves to the requested value.

        Args:
            domain: Fully-qualified record name.
            type: DNS record type. A and AAAA are supported for readiness checks.
            value: Expected public value.
            backend: DNS provider backend. Defaults to godaddy.
            zone: Optional authoritative zone, validated for consistency.
        """
        self._backend(backend)
        domain, _ = self._zone(domain, zone)
        record_type = str(type).upper()
        expected = str(value).strip().rstrip(".").lower()
        family = {"A": socket.AF_INET, "AAAA": socket.AF_INET6}.get(record_type)
        if family is None:
            raise ValueError(
                f"DNS readiness currently supports A and AAAA, not {record_type}"
            )
        try:
            answers = socket.getaddrinfo(domain, None, family, socket.SOCK_STREAM)
        except socket.gaierror:
            return False
        values = {str(item[4][0]).strip().rstrip(".").lower() for item in answers}
        return expected in values

    def delete(
        self,
        domain,
        *,
        type="A",
        value=None,
        backend="godaddy",
        zone=None,
    ):
        """Delete one DNS record name/type pair.

        Args:
            domain: Fully-qualified record name.
            type: DNS record type. Defaults to A.
            value: Accepted for recipe symmetry; GoDaddy v1 deletes by name/type.
            backend: DNS provider backend. Defaults to godaddy.
            zone: Authoritative DNS zone. Defaults to domain.
        """
        del value
        self._backend(backend)
        domain, zone = self._zone(domain, zone)
        record_type = str(type).upper()
        name = self._record_name(domain, zone)
        url = (
            "https://api.godaddy.com/v1/domains/"
            f"{quote(zone, safe='')}/records/{quote(record_type, safe='')}/"
            f"{quote(name, safe='@._-')}"
        )
        self._request("DELETE", url)
        return {
            "domain": domain,
            "zone": zone,
            "type": record_type,
            "backend": "godaddy",
        }
