from types import SimpleNamespace


def test_nested_mapping_and_sequence_traversal(gateway):
    gateway.context["response"] = {
        "payload": {"chargers": [{"serial": "A"}, {"serial": "B"}]}
    }
    assert gateway.resolve("[response payload chargers 1 serial]") == "B"


def test_object_attribute_traversal(gateway):
    gateway.context["charger"] = SimpleNamespace(serial="ABC")
    assert gateway.resolve("[charger serial]") == "ABC"
