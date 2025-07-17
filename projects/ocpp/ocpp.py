# file: projects/ocpp/ocpp.py
"""Generic OCPP helper utilities shared across CSMS and EVCS."""

import json

from gway import gw


def _as_dict(data):
    """Return ``data`` parsed from JSON if it's a text string."""
    if isinstance(data, (str, bytes, bytearray)):
        try:
            data = json.loads(data)
        except Exception:
            return {}
    return data


def authorize_balance(**record):
    """Backward wrapper for :func:`gw.ocpp.rfid.authorize_balance`."""
    return gw.ocpp.rfid.authorize_balance(record=record)


def is_abnormal_status(status: str, error_code: str) -> bool:
    return gw.ocpp.csms.is_abnormal_status(status, error_code)


def get_charger_state(cid, tx, ws_live, raw_hb):
    return gw.ocpp.csms.get_charger_state(cid, _as_dict(tx), ws_live, raw_hb)


def dispatch_action(charger_id: str, action: str):
    return gw.ocpp.csms.dispatch_action(charger_id, action)


# Calculation tools

def extract_meter(tx):
    return gw.ocpp.csms.extract_meter(_as_dict(tx))


def power_consumed(tx):
    return gw.ocpp.csms.power_consumed(_as_dict(tx))


def archive_energy(charger_id, transaction_id, meter_values):
    return gw.ocpp.csms.archive_energy(
        charger_id, transaction_id, _as_dict(meter_values)
    )


def archive_transaction(charger_id, tx):
    return gw.ocpp.csms.archive_transaction(charger_id, _as_dict(tx))


def purge(*, database: bool = False, logs: bool = False):
    return gw.ocpp.csms.purge(database=database, logs=logs)


# ---------------------------------------------------------------------------
# Dashboard and view aliases
# ---------------------------------------------------------------------------



def view_dashboard(**_):
    """Landing page linking to sub-project dashboards."""
    links = [
        ("CSMS Status", "/ocpp/csms/active-chargers"),
        ("Charger Summary", "/ocpp/data/summary"),
        ("Energy Time Series", "/ocpp/data/time-series"),
        ("CP Simulator", "/ocpp/evcs/cp-simulator"),
    ]
    html = ["<h1>OCPP Dashboard</h1>", "<ul>"]
    html.extend(f'<li><a href="{url}">{label}</a></li>' for label, url in links)
    html.append("</ul>")
    return "\n".join(html)


def view_active_chargers(*args, **kwargs):
    return gw.ocpp.csms.view_active_chargers(*args, **kwargs)


def view_charger_detail(*args, **kwargs):
    return gw.ocpp.csms.view_charger_detail(*args, **kwargs)


def view_energy_graph(*args, **kwargs):
    return gw.ocpp.csms.view_energy_graph(*args, **kwargs)


def view_charger_summary(*args, **kwargs):
    return gw.ocpp.data.view_charger_summary(*args, **kwargs)


def view_charger_details(*args, **kwargs):
    return gw.ocpp.data.view_charger_details(*args, **kwargs)


def view_time_series(*args, **kwargs):
    return gw.ocpp.data.view_time_series(*args, **kwargs)


def view_cp_simulator(*args, **kwargs):
    return gw.ocpp.evcs.view_cp_simulator(*args, **kwargs)
