"""Notebook and embedded-Python compatibility contracts for GWAY."""

from gway import Gateway, gw


def test_public_gateway_imports_are_notebook_ready():
    assert isinstance(gw, Gateway)
    assert callable(gw)
    assert callable(Gateway())


def test_gateway_accepts_arbitrary_native_python_objects():
    runtime = Gateway()

    class FrameLike:
        pass

    frame = FrameLike()

    def report(data):
        return data

    runtime.report = runtime.wrap("report_data", report)

    assert runtime("report", frame) is frame


def test_gateway_context_can_hold_application_client_for_commands():
    runtime = Gateway()

    class ArthexisClient:
        def charger_report(self):
            return {"chargers": 3}

    client = ArthexisClient()
    runtime.context["arthexis"] = client

    def report_arthexis(arthexis):
        return arthexis.charger_report()

    runtime.report_arthexis = runtime.wrap("report_arthexis", report_arthexis)

    assert runtime("report_arthexis") == {"chargers": 3}
