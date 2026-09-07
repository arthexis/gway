import pytest

from gway import Gway, gw, gway


def test_public_gway_facade_is_stable_singleton():
    assert isinstance(gway, Gway)
    assert gw is gway


def test_managed_namespace_is_reserved_until_dispatcher_exists():
    with pytest.raises(AttributeError, match="managed project access is not implemented yet"):
        _ = gway.wireguard
