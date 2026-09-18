from gway import Gateway


def test_wrap_is_canonical_gateway_normalization_entry_point():
    assert Gateway.wrap_callable is Gateway.wrap
