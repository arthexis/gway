from pathlib import Path

import pytest

from gway.recipes import load_recipe
from gway.tokens import token_value


@pytest.fixture
def recipe_values():
    def load(path):
        commands, _ = load_recipe(Path("sampler/arthexis") / path)
        return [
            [token_value(token) for token in command["tokens"]] for command in commands
        ]

    return load
