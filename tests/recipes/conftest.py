import pytest

from gway.tokens import Token


@pytest.fixture
def token_values():
    def values(command):
        return [token.value if isinstance(token, Token) else token for token in command["tokens"]]
    return values
