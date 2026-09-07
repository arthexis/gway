from gway import Gway, gw, gway


def test_public_gway_facade_is_stable_singleton():
    assert isinstance(gway, Gway)
    assert gw is gway


def test_managed_namespace_is_reserved_until_dispatcher_exists():
    try:
        gway.wireguard
    except AttributeError as exc:
        assert "managed project access is not implemented yet" in str(exc)
    else:
        raise AssertionError("expected unresolved managed namespace to fail explicitly")
