import pytest


@pytest.fixture
def make_ping_node():
    class PingNode:
        def __init__(self, result="pong"):
            self.result = result

        def ping(self):
            return self.result

    return PingNode
