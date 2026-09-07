from gway import gw, gway


def test_preferred_and_compatibility_imports_share_singleton():
    assert gw is gway
