def test_wrap_publishes_scalar_result_under_subject(gateway):
    def get_charger():
        return "CHG001"

    wrapped = gateway.wrap("get_charger", get_charger)
    assert wrapped() == "CHG001"
    assert gateway.results["charger"] == "CHG001"


def test_wrap_publishes_mapping_result_to_context(gateway):
    def inspect_charger():
        return {"serial": "CHG001", "online": True}

    gateway.wrap("inspect_charger", inspect_charger)()
    assert gateway.context["serial"] == "CHG001"
    assert gateway.context["online"] is True
