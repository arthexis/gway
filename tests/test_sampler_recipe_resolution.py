from gway import Gateway
from gway.recipe.resolve import resolve_recipe_stage
from gway.tokens import tokenize


def test_sampler_recipe_extends_loaded_operation_namespace():
    runtime = Gateway()
    tokens = tokenize("wire watchtower --public-address 192.0.2.10")
    resolved = resolve_recipe_stage(runtime, tokens, pipeline=None)
    assert resolved is not None
    path, arguments, remaining = resolved
    assert path.as_posix().endswith("/sampler/wire/watchtower.rx")
    assert [getattr(token, "value", token) for token in arguments] == [
        "--public-address", "192.0.2.10"
    ]
    assert remaining == []
    assert runtime.ops.resolve("wire.server.check") is not None


def test_exact_operation_still_shadows_sampler_recipe():
    runtime = Gateway()
    runtime.exact = runtime.wrap("wire.watchtower", lambda: "operation")
    tokens = tokenize("wire watchtower")
    assert resolve_recipe_stage(runtime, tokens, pipeline=None) is None
