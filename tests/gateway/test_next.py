import pytest


def test_gateway_next_advances_last_iterator_without_republishing(gateway):
    iterator = iter(["A", "B"])
    gateway.results.insert("chargers", iterator)
    history_size = len(gateway.results.history)

    assert gateway.last is iterator
    assert gateway.next() == "A"
    assert gateway.last is iterator
    assert len(gateway.results.history) == history_size

    assert gateway.next() == "B"
    assert gateway.last is iterator
    assert len(gateway.results.history) == history_size


def test_gateway_next_can_target_named_subject(gateway):
    iterator = iter([1, 2])
    gateway.results.insert("chargers", iterator)

    assert gateway.next("chargers") == 1
    assert gateway.next("chargers") == 2


def test_gateway_next_raises_for_non_iterator(gateway):
    gateway.results.insert("value", [1, 2, 3])

    with pytest.raises(TypeError):
        gateway.next("value")


def test_gateway_next_propagates_stop_iteration(gateway):
    gateway.results.insert("chargers", iter([]))

    with pytest.raises(StopIteration):
        gateway.next()


def test_gateway_next_supports_python_style_default(gateway):
    gateway.results.insert("chargers", iter([]))

    assert gateway.next(default=None) is None
    assert gateway.last is gateway.results["chargers"]
