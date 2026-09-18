import pytest
from gway import gw

@pytest.fixture(autouse=True)
def reset_gw_resource():
    orig = gw.resource
    yield
    gw.resource = orig
