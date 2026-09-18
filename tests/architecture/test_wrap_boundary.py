from gway import Gateway


def test_wrap_is_canonical_gateway_normalization_entry_point():
    assert callable(Gateway.wrap)


def test_wrap_callable_legacy_name_is_removed():
    assert not hasattr(Gateway, "wrap_callable")
