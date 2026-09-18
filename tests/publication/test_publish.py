from gway.publication import publish


def test_scalar_result_publishes_under_subject(gateway):
    assert publish(gateway, "charger", "CHG001") == "CHG001"
    assert gateway.results["charger"] == "CHG001"


def test_mapping_result_is_preserved_under_subject(gateway):
    result = {"serial": "CHG001", "online": True}

    assert publish(gateway, "charger", result) is result
    assert gateway.results["charger"] is result
    assert "serial" not in gateway.results
    assert "online" not in gateway.results


def test_mapping_result_is_merged_into_context(gateway):
    result = {"serial": "CHG001", "online": True}

    publish(gateway, "charger", result)
    assert gateway.context["serial"] == "CHG001"
    assert gateway.context["online"] is True


def test_repeated_publication_replaces_same_subject(gateway):
    publish(gateway, "charger", "CHG001")
    publish(gateway, "charger", "CHG002")

    assert gateway.results["charger"] == "CHG002"


def test_none_result_is_not_published(gateway):
    assert publish(gateway, "charger", None) is None
    assert "charger" not in gateway.results


def test_missing_subject_is_not_published(gateway):
    assert publish(gateway, None, "value") == "value"
    assert "value" not in gateway.results.values()
