def test_gateway_last_tracks_most_recent_operation(gateway):
    def first():
        return "A"

    def second():
        return "B"

    gateway.first = gateway.wrap("get_first", first)
    gateway.second = gateway.wrap("get_second", second)

    gateway("first")
    assert gateway.last == "A"

    gateway("second")
    assert gateway.last == "B"
    assert gateway.results[-2] == "A"
    assert gateway.results[-1] == "B"


def test_gateway_last_can_be_none_after_completed_operation(gateway):
    def noop():
        return None

    gateway.noop = gateway.wrap("do_noop", noop)
    gateway("noop")

    assert gateway.last is None
    assert gateway.results[-1] is None
