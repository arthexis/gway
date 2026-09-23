from gway.environment import TRANSITIONAL_SEMANTIC_ENVIRONMENT


def test_transitional_semantic_environment_inventory_is_empty():
    assert TRANSITIONAL_SEMANTIC_ENVIRONMENT == frozenset()
