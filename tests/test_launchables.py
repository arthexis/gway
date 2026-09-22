from gway.gateway import Gateway


def test_gateway_operations_are_indexed_as_launchables():
    runtime = Gateway()

    def ping():
        return "pong"

    runtime.wrap("ping", ping)

    launchable = runtime.launchables["ping"]

    assert launchable.kind == "operation"
    assert launchable.target == "ping"
    assert launchable.command == ("{python}", "-m", "gway", "ping")
