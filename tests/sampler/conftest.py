import pytest

from gway.recipe import load_recipe
from gway.sampler import root as sampler_root
from gway.tokens import token_value


@pytest.fixture
def sampler_path():
    def resolve(relative):
        return sampler_root() / relative

    return resolve


@pytest.fixture
def recipe_commands(sampler_path):
    def render(relative):
        commands, _ = load_recipe(sampler_path(relative))
        return [
            " ".join(token_value(token) for token in command["tokens"])
            for command in commands
        ]

    return render
