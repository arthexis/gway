import pytest

from gway import Gateway


@pytest.fixture
def gateway():
    runtime = Gateway()
    runtime.context.clear()
    runtime.results.clear()
    return runtime
