import os
import subprocess
import sys

import gway
from gway import Gateway


def fresh_gateway(**kwargs):
    gateway = Gateway(**kwargs)
    gateway.context.clear()
    gateway.results.clear()
    return gateway


def test_import_gway():
    assert isinstance(gway.gw, Gateway)


def test_gateway_resolves_process_environment(monkeypatch):
    monkeypatch.setenv("GWAY_SMOKE_VALUE", "ready")
    gateway = fresh_gateway()
    assert gateway.resolve("[GWAY_SMOKE_VALUE]") == "ready"


def test_wrap_callable_publishes_semantic_subject():
    gateway = fresh_gateway()

    def create_charger(serial: str):
        return {"serial": serial}

    wrapped = gateway.wrap_callable("create_charger", create_charger)
    assert wrapped("ABC") == {"serial": "ABC"}
    assert gateway.context["serial"] == "ABC"


def test_subject_uses_verb_subject_vocabulary():
    assert Gateway.subject("create_charger") == "charger"
    assert Gateway.subject("device.create_charger") == "charger"


def test_cli_help_runs():
    completed = subprocess.run(
        [sys.executable, "-m", "gway", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0
    assert "command-dispatch and composition core" in completed.stdout
