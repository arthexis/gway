import pytest

from gway import Gateway
from gway import sampler


class FakeOdooClient:
    calls = []
    settings = []

    def __init__(self, **settings):
        type(self).settings.append(settings)

    def execute(self, model, method, args=(), kwargs=None):
        type(self).calls.append(
            {
                "model": model,
                "method": method,
                "args": list(args),
                "kwargs": {} if kwargs is None else dict(kwargs),
            }
        )
        if method == "fields_get":
            return {"name": {"string": "Name", "type": "char"}}
        return [{"id": 7, "name": "SO007"}]


@pytest.fixture(autouse=True)
def reset_fake_odoo():
    FakeOdooClient.calls = []
    FakeOdooClient.settings = []


def credentials():
    return {
        "odoo_url": "https://odoo.example.test",
        "odoo_database": "demo",
        "odoo_username": "reader@example.test",
        "odoo_password": "secret",
    }


def test_odoo_sampler_is_lazy_and_registers_on_resolution_miss(monkeypatch):
    module = sampler.load("odoo")
    monkeypatch.setattr(module, "XmlRpcOdooClient", FakeOdooClient)
    gateway = Gateway(context=credentials())

    assert gateway.ops.resolve("query.odoo") is None

    result = gateway("query odoo sale.order")

    assert result == [{"id": 7, "name": "SO007"}]
    assert gateway.ops.resolve("query.odoo") is not None
    assert gateway.ops.resolve("fields.odoo") is not None
    assert FakeOdooClient.calls == [
        {
            "model": "sale.order",
            "method": "search_read",
            "args": [[]],
            "kwargs": {},
        }
    ]


def test_odoo_query_passes_safe_domain_fields_and_paging():
    module = sampler.load("odoo")
    gateway = Gateway(context=credentials())
    module.register(gateway, client_factory=FakeOdooClient)

    result = gateway.query_odoo(
        "sale.order",
        domain='[["state", "=", "sale"]]',
        fields="name, amount_total",
        limit=5,
        offset=2,
        order="name desc",
    )

    assert result == [{"id": 7, "name": "SO007"}]
    assert FakeOdooClient.calls[-1] == {
        "model": "sale.order",
        "method": "search_read",
        "args": [[["state", "=", "sale"]]],
        "kwargs": {
            "fields": ["name", "amount_total"],
            "limit": 5,
            "offset": 2,
            "order": "name desc",
        },
    }


def test_odoo_fields_returns_structured_metadata():
    module = sampler.load("odoo")
    gateway = Gateway(context=credentials())
    module.register(gateway, client_factory=FakeOdooClient)

    result = gateway.fields_odoo("sale.order", attributes=("string", "type"))

    assert result == {"name": {"string": "Name", "type": "char"}}
    assert FakeOdooClient.calls[-1] == {
        "model": "sale.order",
        "method": "fields_get",
        "args": [],
        "kwargs": {"attributes": ["string", "type"]},
    }


def test_odoo_domain_rejects_python_expression_syntax():
    module = sampler.load("odoo")

    with pytest.raises(ValueError, match="valid JSON"):
        module.parse_domain("[('state', '=', 'sale')]")


def test_odoo_read_operations_are_non_mutating():
    module = sampler.load("odoo")
    gateway = Gateway()
    module.register(gateway, client_factory=FakeOdooClient)

    assert gateway.ops.resolve("query.odoo").mutates is False
    assert gateway.ops.resolve("fields.odoo").mutates is False


def test_odoo_client_authenticates_and_uses_standard_xmlrpc_endpoints():
    module = sampler.load("odoo")
    observed = {"proxies": []}

    class Common:
        def authenticate(self, database, username, password, context):
            observed["auth"] = (database, username, password, context)
            return 42

    class Models:
        def execute_kw(self, *args):
            observed["execute"] = args
            return [{"id": 1}]

    def proxy_factory(url, **kwargs):
        observed["proxies"].append((url, kwargs))
        return Common() if url.endswith("/common") else Models()

    client = module.XmlRpcOdooClient(
        url="https://odoo.example.test/",
        database="demo",
        username="reader",
        password="secret",
        proxy_factory=proxy_factory,
    )

    assert client.execute("res.partner", "search_read", [[]], {"limit": 1}) == [
        {"id": 1}
    ]
    assert observed["proxies"] == [
        ("https://odoo.example.test/xmlrpc/2/common", {"allow_none": True}),
        ("https://odoo.example.test/xmlrpc/2/object", {"allow_none": True}),
    ]
    assert observed["auth"] == ("demo", "reader", "secret", {})
    assert observed["execute"] == (
        "demo",
        42,
        "secret",
        "res.partner",
        "search_read",
        [[]],
        {"limit": 1},
    )


def test_odoo_client_rejects_failed_authentication():
    module = sampler.load("odoo")

    class Common:
        def authenticate(self, *_args):
            return False

    def proxy_factory(_url, **_kwargs):
        return Common()

    with pytest.raises(module.OdooAuthenticationError, match="authentication failed"):
        module.XmlRpcOdooClient(
            url="https://odoo.example.test",
            database="demo",
            username="reader",
            password="wrong",
            proxy_factory=proxy_factory,
        )


def test_odoo_query_preserves_json_domain_through_binding():
    from gway.console import process

    module = sampler.load("odoo")
    gateway = Gateway(context=credentials())
    module.register(gateway, client_factory=FakeOdooClient)

    _, result = process(
        [[
            "query",
            "odoo",
            "sale.order",
            "--domain",
            '[["state","=","sale"]]',
        ]],
        gw_instance=gateway,
    )

    assert result == [{"id": 7, "name": "SO007"}]
    assert FakeOdooClient.calls[-1]["args"] == [
        [["state", "=", "sale"]]
    ]
