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



def view_ocpp_dashboard(*, _title="OCPP Dashboard", **_):
    """Landing page with a summary card for each sub-project."""

    active = len(gw.ocpp.data.get_active_chargers())
    summary = gw.ocpp.data.get_summary()
    chargers = len(summary)
    sessions = sum(r.get("sessions", 0) for r in summary)
    energy = round(sum(r.get("energy", 0.0) for r in summary), 3)
    sim_state = gw.ocpp.evcs.get_simulator_state(refresh_file=True)
    s1 = "Running" if sim_state.get(1, {}).get("running") else "Stopped"
    s2 = "Running" if sim_state.get(2, {}).get("running") else "Stopped"
    sim_running = f"CP1: {s1}<br>CP2: {s2}"

    links = [
        ("CSMS Status", "/ocpp/active-chargers",
         f"Active chargers: {active}"),
        ("Charger Summary", "/ocpp/charger-summary",
         f"Chargers: {chargers}<br>Sessions: {sessions}"),
        ("Energy Time Series", "/ocpp/time-series",
         f"Total Energy: {energy} kWh"),
        ("CP Simulator", "/ocpp/evcs/cp-simulator",
         f"Simulator: {sim_running}"),
    ]

    html = ["<h1>OCPP Dashboard</h1>"]
    html.append(
        "<style>"
        ".ocpp-cards{display:flex;flex-wrap:wrap;gap:1em;margin:1em 0;}"
        ".ocpp-card{display:block;padding:1em;border:1px solid var(--muted,#ccc);border-radius:8px;"
        "background:var(--card-bg,#f9f9f9);box-shadow:0 2px 4px rgba(0,0,0,0.1);width:16em;"
        "text-decoration:none;color:inherit;}"
        ".ocpp-card h2{margin-top:0;font-size:1.2em;}"
        ".ocpp-card p{margin:.4em 0;}"
        "</style>"
    )
    html.append('<div class="ocpp-cards">')
    for label, url, info in links:
        html.append(
            f'<a class="ocpp-card" href="{url}"><h2>{label}</h2><p>{info}</p></a>'
        )
    html.append('</div>')

    html.append('<h2>Resources</h2><ul>')
    html.append(
        '<li><a href="https://www.openchargealliance.org/" target="_blank">'
        'Open Charge Alliance</a></li>'
    )
    html.append(
        '<li><a href="https://github.com/OpenChargeAlliance/ocpp" target="_blank">'
        'OCPP Specification</a></li>'
    )
    html.append('</ul>')

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


def view_cp_simulator(*args, _title="CP Simulator", **kwargs):
    return gw.ocpp.evcs.view_cp_simulator(*args, **kwargs)


def view_evcs(view: str | None = None, *args, **kwargs):
    """Delegate ``/ocpp/evcs/<view>`` routes to :mod:`ocpp.evcs` views."""
    target = (view or "cp-simulator").replace("-", "_")
    func = getattr(gw.ocpp.evcs, f"view_{target}", None)
    if not callable(func):
        return gw.web.error.redirect(
            f"View not found: {target} in ocpp.evcs"
        )
    return func(*args, **kwargs)


def view_manage_rfids(*args, _title="Manage RFIDs", **kwargs):
    """Delegate to :func:`gw.ocpp.rfid.view_manage_rfids`."""
    return gw.ocpp.rfid.view_manage_rfids(*args, **kwargs)


