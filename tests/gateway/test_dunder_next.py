def test_dunder_next_advances_last_iterator(gateway):
    iterator = iter(["A", "B"])
    gateway.results.insert("chargers", iterator)
    history_size = len(gateway.results.history)

    assert next(gateway) == "A"
    assert gateway.last is iterator
    assert len(gateway.results.history) == history_size

    assert next(gateway) == "B"
    assert gateway.last is iterator
    assert len(gateway.results.history) == history_size


def test_dunder_next_propagates_stop_iteration(gateway):
    gateway.results.insert("chargers", iter([]))

    try:
        next(gateway)
    except StopIteration:
        pass
    else:
        raise AssertionError("next(gateway) should propagate StopIteration")
