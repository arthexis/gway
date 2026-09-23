import pytest

from gway.remote.acceptance import _protocol, accept


@pytest.mark.parametrize(
    ("resource", "expected"),
    [
        ("https://remote.example.test/mcp", "mcp"),
        ("https://remote.example.test/mcp/", "mcp"),
        ("https://remote.example.test", "mcp"),
    ],
)
def test_protocol_is_semantically_optional(resource, expected):
    assert _protocol(resource) == expected


def test_explicit_protocol_overrides_resource_path():
    assert _protocol("https://remote.example.test/custom", "mcp") == "mcp"


def test_remote_accept_dispatches_to_protocol_sampler():
    calls = []

    class Runtime:
        def _run_sampler_recipe(self, name, **context):
            calls.append((name, context))
            return {"ok": True}

    result = accept(Runtime(), "https://remote.example.test/mcp")

    assert result == {"ok": True}
    assert calls == [
        (
            "mcp/accept",
            {
                "resource": "https://remote.example.test/mcp",
                "protocol": "mcp",
            },
        )
    ]
