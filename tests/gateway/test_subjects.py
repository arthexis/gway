from gway import Gateway


def test_subject_uses_verb_subject_vocabulary():
    assert Gateway.subject("create_charger") == "charger"
    assert Gateway.subject("device.create_charger") == "charger"
