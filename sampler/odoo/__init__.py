"""Lazy Odoo sampler for authenticated read-only model access."""

from __future__ import annotations

import json
from urllib.parse import urlsplit
from xmlrpc.client import ServerProxy

from gway.binding import Literal


class OdooAuthenticationError(RuntimeError):
    """Raised when Odoo rejects configured credentials."""


def _base_url(value):
    url = str(value).strip().rstrip("/")
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("odoo_url must be an absolute http(s) URL")
    return url


def _json_value(value):
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return value


def parse_domain(value):
    """Return an Odoo domain without evaluating Python expressions."""
    if value in (None, "", (), []):
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exception:
            raise ValueError("odoo domain must be valid JSON") from exception
    if not isinstance(value, (list, tuple)):
        raise TypeError("odoo domain must be a JSON array")
    return _json_value(value)


def _names(value):
    if value in (None, "", (), []):
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return [str(item).strip() for item in value if str(item).strip()]


class XmlRpcOdooClient:
    """Small Odoo 16 XML-RPC transport boundary."""

    def __init__(
        self,
        *,
        url,
        database,
        username,
        password,
        proxy_factory=ServerProxy,
    ):
        self.url = _base_url(url)
        self.database = str(database)
        self.username = str(username)
        self.password = str(password)
        common = proxy_factory(f"{self.url}/xmlrpc/2/common", allow_none=True)
        uid = common.authenticate(
            self.database,
            self.username,
            self.password,
            {},
        )
        if not uid:
            raise OdooAuthenticationError("Odoo authentication failed")
        self.uid = uid
        self._models = proxy_factory(
            f"{self.url}/xmlrpc/2/object",
            allow_none=True,
        )

    def execute(self, model, method, args=(), kwargs=None):
        """Execute one authenticated Odoo model call."""
        return self._models.execute_kw(
            self.database,
            self.uid,
            self.password,
            str(model),
            str(method),
            list(args),
            {} if kwargs is None else dict(kwargs),
        )


class Controller:
    """Expose read-only Odoo model operations through Gway."""

    def __init__(self, gateway, *, client_factory=None):
        self.gateway = gateway
        self.client_factory = client_factory or XmlRpcOdooClient

    def _client(
        self,
        *,
        odoo_url,
        odoo_database,
        odoo_username,
        odoo_password,
    ):
        return self.client_factory(
            url=odoo_url,
            database=odoo_database,
            username=odoo_username,
            password=odoo_password,
        )

    def query(
        self,
        model,
        *,
        domain: Literal = (),
        fields=(),
        limit=None,
        offset=0,
        order=None,
        odoo_url,
        odoo_database,
        odoo_username,
        odoo_password,
        mutate=False,
    ):
        """Query readable records from one Odoo model.

        Args:
            model: Odoo model identity, for example sale.order.
            domain: JSON-encoded Odoo domain array or an already-structured sequence.
            fields: Requested field names, as a sequence or comma-separated string.
            limit: Optional maximum record count.
            offset: Optional record offset.
            order: Optional Odoo order expression.
        """
        del mutate
        model = str(model).strip()
        if not model:
            raise ValueError("odoo model must be non-empty")
        kwargs = {}
        selected_fields = _names(fields)
        if selected_fields:
            kwargs["fields"] = selected_fields
        if limit is not None:
            kwargs["limit"] = int(limit)
        if offset:
            kwargs["offset"] = int(offset)
        if order is not None:
            kwargs["order"] = str(order)

        client = self._client(
            odoo_url=odoo_url,
            odoo_database=odoo_database,
            odoo_username=odoo_username,
            odoo_password=odoo_password,
        )
        return client.execute(
            model,
            "search_read",
            [parse_domain(domain)],
            kwargs,
        )

    def fields(
        self,
        model,
        *,
        attributes=("string", "type", "required", "readonly", "relation"),
        odoo_url,
        odoo_database,
        odoo_username,
        odoo_password,
        mutate=False,
    ):
        """Return readable Odoo field metadata for one model."""
        del mutate
        model = str(model).strip()
        if not model:
            raise ValueError("odoo model must be non-empty")
        kwargs = {}
        selected = _names(attributes)
        if selected:
            kwargs["attributes"] = selected

        client = self._client(
            odoo_url=odoo_url,
            odoo_database=odoo_database,
            odoo_username=odoo_username,
            odoo_password=odoo_password,
        )
        return client.execute(model, "fields_get", [], kwargs)


def register(gateway, *, client_factory=None):
    """Register the optional Odoo read surface on one Gateway."""
    controller = Controller(gateway, client_factory=client_factory)
    gateway._odoo_controller = controller
    gateway.query_odoo = gateway.wrap(
        "query.odoo",
        controller.query,
        op="query",
        sub="odoo",
    )
    gateway.fields_odoo = gateway.wrap(
        "fields.odoo",
        controller.fields,
        op="fields",
        sub="odoo",
    )
    return controller


__all__ = [
    "Controller",
    "OdooAuthenticationError",
    "XmlRpcOdooClient",
    "parse_domain",
    "register",
]
