# file: projects/ocpp/ocpp.py
"""Generic OCPP helper utilities shared across CSMS and EVCS."""

import json
import os
import shutil
import uuid
import asyncio
import sys
import importlib
from datetime import datetime
from typing import Dict, Optional
from fastapi import WebSocket
from bottle import HTTPError
from gway import gw

# Shared state trackers
_csms_loop: Optional[asyncio.AbstractEventLoop] = None
_transactions: Dict[str, dict] = {}
_active_cons: Dict[str, WebSocket] = {}
_latest_heartbeat: Dict[str, str] = {}
_abnormal_status: Dict[str, dict] = {}
_msg_log: Dict[str, list] = {}


def _as_dict(data):
    """Return ``data`` parsed from JSON if it's a text string."""
    if isinstance(data, (str, bytes, bytearray)):
        try:
            data = json.loads(data)
        except Exception:
            return {}
    return data


def authorize_balance(**record):
    """Default RFID validator: allow if balance >= 1."""
    try:
        return float(record.get("balance", "0")) >= 1
    except Exception:
        return False


def is_abnormal_status(status: str, error_code: str) -> bool:
    """Return True if the status/errorCode combination is abnormal."""
    status = (status or "").capitalize()
    error_code = (error_code or "").capitalize()
    if status in ("Available", "Preparing") and error_code in ("Noerror", "", None):
        return False
    if status in ("Faulted", "Unavailable", "Suspendedev", "Suspended", "Removed"):
        return True
    if error_code not in ("Noerror", "", None):
        return True
    return False


def get_charger_state(cid, tx, ws_live, raw_hb):
    """Compute charger state string based on activity and errors."""
    tx = _as_dict(tx)
    if cid in _abnormal_status:
        return "error"
    if ws_live and tx and not tx.get("syncStop"):
        return "online"
    if ws_live and (not tx or tx.get("syncStop")):
        return "available"
    return "unknown"


def dispatch_action(charger_id: str, action: str):
    """Send a remote action request over an active websocket."""
    ws = _active_cons.get(charger_id)
    if not ws:
        raise HTTPError(404, "No active connection")
    msg_id = str(uuid.uuid4())
    msg_text = None
    if action == "remote_stop":
        tx = _transactions.get(charger_id)
        if not tx:
            raise HTTPError(404, "No transaction to stop")
        msg_text = json.dumps([2, msg_id, "RemoteStopTransaction", {"transactionId": tx["transactionId"]}])
        coro = ws.send_text(msg_text)
    elif action.startswith("reset_"):
        _, mode = action.split("_", 1)
        msg_text = json.dumps([2, msg_id, "Reset", {"type": mode.capitalize()}])
        coro = ws.send_text(msg_text)
    elif action == "disconnect":
        coro = ws.close(code=1000, reason="Admin disconnect")
    else:
        raise HTTPError(400, f"Unknown action: {action}")
    if _csms_loop:
        _csms_loop.call_soon_threadsafe(lambda: _csms_loop.create_task(coro))
    else:
        gw.warn("No CSMS event loop; action not sent")
    if msg_text:
        _msg_log.setdefault(charger_id, []).append(f"< {msg_text}")
    return {"status": "requested", "messageId": msg_id}


# Calculation tools

def extract_meter(tx):
    """Return latest Energy.Active.Import.Register (kWh) value."""
    tx = _as_dict(tx)
    if not tx:
        return "-"
    if tx.get("meterStop") is not None:
        try:
            return float(tx["meterStop"]) / 1000.0
        except Exception:
            return tx["meterStop"]
    mv = tx.get("MeterValues", [])
    if mv:
        last_mv = mv[-1]
        for sv in last_mv.get("sampledValue", []):
            if sv.get("measurand") == "Energy.Active.Import.Register":
                val = sv.get("value")
                try:
                    val_f = float(val)
                    if sv.get("unit") == "Wh":
                        val_f = val_f / 1000.0
                    return val_f
                except Exception:
                    return val
    return "-"


def power_consumed(tx):
    """Calculate kWh consumed from transaction meter data."""
    tx = _as_dict(tx)
    if not tx:
        return 0.0
    meter_values = tx.get("MeterValues", [])
    energy_vals = []
    for entry in meter_values:
        for sv in entry.get("sampledValue", []):
            if sv.get("measurand") == "Energy.Active.Import.Register":
                val = sv.get("value")
                try:
                    val_f = float(val)
                    if sv.get("unit") == "Wh":
                        val_f = val_f / 1000.0
                    energy_vals.append(val_f)
                except Exception:
                    pass
    meter_start = tx.get("meterStart")
    start_val = None
    if energy_vals:
        start_val = energy_vals[0]
    elif meter_start is not None:
        try:
            start_val = float(meter_start) / 1000.0
        except Exception:
            start_val = None
    end_val = None
    if energy_vals:
        end_val = energy_vals[-1]
    elif tx.get("meterStop") is not None:
        try:
            end_val = float(tx["meterStop"]) / 1000.0
        except Exception:
            end_val = None
    if start_val is not None and end_val is not None:
        return round(end_val - start_val, 3)
    meter_stop = tx.get("meterStop")
    try:
        if meter_start is not None and meter_stop is not None:
            return round(float(meter_stop) / 1000.0 - float(meter_start) / 1000.0, 3)
        if meter_start is not None:
            return 0.0
    except Exception:
        pass
    return 0.0


def archive_energy(charger_id, transaction_id, meter_values):
    """Store MeterValues for a charger/transaction as a dated JSON file."""
    meter_values = _as_dict(meter_values)
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    base = gw.resource("work", "etron", "graphs", charger_id)
    os.makedirs(base, exist_ok=True)
    file_path = os.path.join(base, f"{date_str}_{transaction_id}.json")
    with open(file_path, "w") as f:
        json.dump(meter_values, f, indent=2)
    return file_path


def archive_transaction(charger_id, tx):
    """Write a transaction record as JSON in work/ocpp/records."""
    tx = _as_dict(tx)
    try:
        connector = tx.get("connectorId", 0)
        txn_id = tx.get("transactionId")
        if txn_id is None:
            return None
        base = gw.resource("work", "ocpp", "records", charger_id)
        os.makedirs(base, exist_ok=True)
        file_path = os.path.join(base, f"{connector}_{txn_id}.dat")
        with open(file_path, "w") as f:
            json.dump(tx, f, indent=2)
        return file_path
    except Exception:
        gw.exception("Failed to archive transaction")
        return None


def purge(*, database: bool = False, logs: bool = False):
    """Clear in-memory state and optionally purge database and logs."""
    _transactions.clear()
    _active_cons.clear()
    _latest_heartbeat.clear()
    _abnormal_status.clear()
    _msg_log.clear()
    gw.info("[OCPP] In-memory state purged.")
    if database:
        conn = gw.ocpp.data.open_db()
        gw.sql.execute("DELETE FROM transactions", connection=conn)
        gw.sql.execute("DELETE FROM meter_values", connection=conn)
        gw.sql.execute("DELETE FROM errors", connection=conn)
        gw.info("[OCPP] Database records purged.")
    if logs:
        for path in [gw.resource("work", "ocpp", "records"), gw.resource("work", "etron", "graphs")]:
            if os.path.isdir(path):
                shutil.rmtree(path)
                os.makedirs(path, exist_ok=True)
        gw.info("[OCPP] Log files purged.")


# ---------------------------------------------------------------------------
# Dashboard and view aliases
# ---------------------------------------------------------------------------

csms = importlib.import_module('ocpp_csms')
data = importlib.import_module('ocpp_data')
evcs = importlib.import_module('ocpp_evcs')
csms.bind_state(sys.modules[__name__])


def view_dashboard(**_):
    """Landing page linking to sub-project dashboards."""
    links = [
        ("CSMS Status", "/ocpp/csms/charger-status"),
        ("Charger Summary", "/ocpp/data/summary"),
        ("Energy Time Series", "/ocpp/data/time-series"),
        ("CP Simulator", "/ocpp/evcs/cp-simulator"),
    ]
    html = ["<h1>OCPP Dashboard</h1>", "<ul>"]
    html.extend(f'<li><a href="{url}">{label}</a></li>' for label, url in links)
    html.append("</ul>")
    return "\n".join(html)


def view_charger_status(*args, **kwargs):
    return csms.view_charger_status(*args, **kwargs)


def view_charger_detail(*args, **kwargs):
    return csms.view_charger_detail(*args, **kwargs)


def view_energy_graph(*args, **kwargs):
    return csms.view_energy_graph(*args, **kwargs)


def view_charger_summary(*args, **kwargs):
    return data.view_charger_summary(*args, **kwargs)


def view_charger_details(*args, **kwargs):
    return data.view_charger_details(*args, **kwargs)


def view_time_series(*args, **kwargs):
    return data.view_time_series(*args, **kwargs)


def view_cp_simulator(*args, **kwargs):
    return evcs.view_cp_simulator(*args, **kwargs)
