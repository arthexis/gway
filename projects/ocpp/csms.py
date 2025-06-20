# projects/ocpp.py

import json
import os
import time
import uuid
import traceback
import asyncio
from datetime import datetime
from fastapi import WebSocket, WebSocketDisconnect
from bottle import HTTPError
from typing import Dict, Optional
from gway import gw


# TODO: Add a back link after operations are sent
# TODO: Allow specifying a different base endpoint path on the server side 
# TODO: Consider if we have to capture additional query params from the evcs


# TODO: Fix the power calculation, seems to show negative numbers, by tracking boot notification and storing in a cdv
#       Store all received data from the notification as keys in the CDV. See attached code for how gw.cdv.store works

def authorize_balance(**record):
    """
    Default OCPP RFID secondary validator: Only authorize if balance >= 1.
    This can be passed directly as the default 'authorize' param.
    The RFID needs to exist already for this to be called in the first place.
    """
    try:
        return float(record.get("balance", "0")) >= 1
    except Exception:
        return False
    

_csms_loop: Optional[asyncio.AbstractEventLoop] = None
_transactions: Dict[str, dict] = {}           # charger_id → latest transaction
_active_cons: Dict[str, WebSocket] = {}      # charger_id → live WebSocket


def setup_app(*,
    app=None,
    allowlist=None,
    denylist=None,  # New parameter for RFID denylist
    location=None,
    authorize=authorize_balance,
):
    """
    Minimal OCPP 1.6 CSMS implementation for conformance testing.
    Supports required Core actions, logs all requests, and accepts all.
    Optional RFID allowlist enables restricted access on Authorize.
    Optional denylist enables explicit denial even if present in allowlist.
    Optional `authorize` hook can be a callable or gw['name'].
    Optional `location` enables per-txn logging to work/etron/records/{location}/{charger}_{txn_id}.dat
    """
    global _transactions, _active_cons

    # Unwrap or create FastAPI app
    oapp = app
    from fastapi import FastAPI as _FastAPI
    if (_is_new_app := not (app := gw.unwrap_one(app, _FastAPI))):
        app = _FastAPI()

    # Compose the validator: prefer explicit callable, then gw[] ref, else default
    validator = None
    if isinstance(authorize, str):
        validator = gw[authorize]
    elif callable(authorize):
        validator = authorize

    def is_authorized_rfid(rfid: str) -> bool:
        # --- DENYLIST logic ---
        if denylist and gw.cdv.validate(denylist, rfid):
            gw.info(f"[OCPP] RFID {rfid!r} is present in denylist. Authorization denied.")
            return False
        # --- ALLOWLIST logic ---
        if not allowlist:
            gw.warn("[OCPP] No RFID allowlist configured — rejecting all authorization requests.")
            return False
        return gw.cdv.validate(allowlist, rfid, validator=validator)

    @app.websocket("/{path:path}")
    async def websocket_ocpp(websocket: WebSocket, path: str):
        global _csms_loop
        _csms_loop = asyncio.get_running_loop()

        charger_id = path.strip("/").split("/")[-1]
        gw.info(f"[OCPP] WebSocket connected: charger_id={charger_id}")

        # negotiate subprotocols
        protos = websocket.headers.get("sec-websocket-protocol", "").split(",")
        protos = [p.strip() for p in protos if p.strip()]
        if "ocpp1.6" in protos:
            await websocket.accept(subprotocol="ocpp1.6")
        else:
            await websocket.accept()

        _active_cons[charger_id] = websocket

        try:
            while True:
                raw = await websocket.receive_text()
                gw.info(f"[OCPP:{charger_id}] → {raw}")
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    gw.warn(f"[OCPP:{charger_id}] Received non-JSON message: {raw!r}")
                    continue

                if isinstance(msg, list) and msg[0] == 2:
                    message_id, action = msg[1], msg[2]
                    payload = msg[3] if len(msg) > 3 else {}
                    gw.debug(f"[OCPP:{charger_id}] Action={action} Payload={payload}")

                    response_payload = {}

                    if action == "Authorize":
                        status = "Accepted" if is_authorized_rfid(payload.get("idTag")) else "Rejected"
                        response_payload = {"idTagInfo": {"status": status}}

                    elif action == "BootNotification":
                        response_payload = {
                            "currentTime": datetime.utcnow().isoformat() + "Z",
                            "interval": 300,
                            "status": "Accepted"
                        }

                    elif action == "Heartbeat":
                        response_payload = {"currentTime": datetime.utcnow().isoformat() + "Z"}

                    elif action == "StartTransaction":
                        now = int(time.time())
                        transaction_id = now
                        _transactions[charger_id] = {
                            "syncStart": 1,
                            "connectorId": payload.get("connectorId"),
                            "idTagStart": payload.get("idTag"),
                            "meterStart": payload.get("meterStart"),
                            "reservationId": payload.get("reservationId", -1),
                            "startTime": now,
                            "startTimeStr": datetime.utcfromtimestamp(now).isoformat() + "Z",
                            "startMs": int(time.time() * 1000) % 1000,
                            "transactionId": transaction_id,
                            "MeterValues": []
                        }
                        response_payload = {
                            "transactionId": transaction_id,
                            "idTagInfo": {"status": "Accepted"}
                        }

                    elif action == "MeterValues":
                        tx = _transactions.get(charger_id)
                        if tx:
                            for entry in payload.get("meterValue", []):
                                ts = entry.get("timestamp")
                                ts_epoch = (
                                    int(datetime.fromisoformat(ts.rstrip("Z")).timestamp())
                                    if ts else int(time.time())
                                )
                                # Prepare a copy of the sampledValue list, normalizing types
                                sampled = []
                                for sv in entry.get("sampledValue", []):
                                    # Only store values we can parse as float
                                    val = sv.get("value")
                                    unit = sv.get("unit", "")
                                    measurand = sv.get("measurand", "")
                                    try:
                                        fval = float(val)
                                        # Convert Wh to kWh
                                        if unit == "Wh":
                                            fval = fval / 1000.0
                                        sampled.append({
                                            "value": fval,
                                            "unit": "kWh" if unit == "Wh" else unit,
                                            "measurand": measurand,
                                            "context": sv.get("context", ""),
                                        })
                                    except Exception:
                                        continue
                                tx["MeterValues"].append({
                                    "timestamp": ts_epoch,
                                    "timestampStr": datetime.utcfromtimestamp(ts_epoch).isoformat() + "Z",
                                    "timeMs": int(time.time() * 1000) % 1000,
                                    "sampledValue": sampled,
                                })
                        response_payload = {}

                    elif action == "StopTransaction":
                        now = int(time.time())
                        tx = _transactions.get(charger_id)
                        if tx:
                            tx.update({
                                "syncStop": 1,
                                "idTagStop": payload.get("idTag"),
                                "meterStop": payload.get("meterStop"),
                                "stopTime": now,
                                "stopTimeStr": datetime.utcfromtimestamp(now).isoformat() + "Z",
                                "stopMs": int(time.time() * 1000) % 1000,
                                "reason": 4,
                                "reasonStr": "Local",
                            })
                            if location:
                                file_path = gw.resource(
                                    "work", "etron", "records", location,
                                    f"{charger_id}_{tx['transactionId']}.dat"
                                )
                                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                                with open(file_path, "w") as f:
                                    json.dump(tx, f, indent=2)
                        response_payload = {"idTagInfo": {"status": "Accepted"}}

                    elif action == "StatusNotification":
                        response_payload = {}

                    else:
                        response_payload = {"status": "Accepted"}

                    # send confirmation
                    response = [3, message_id, response_payload]
                    gw.info(f"[OCPP:{charger_id}] ← {action} => {response_payload}")
                    await websocket.send_text(json.dumps(response))

                elif isinstance(msg, list) and msg[0] == 3:
                    # This is a CALLRESULT; normally safe to ignore unless you send requests to the client
                    gw.debug(f"[OCPP:{charger_id}] Received CALLRESULT: {msg}")
                    continue

                elif isinstance(msg, list) and msg[0] == 4:
                    # This is a CALLERROR; log as info/debug
                    gw.info(f"[OCPP:{charger_id}] Received CALLERROR: {msg}")
                    continue

                else:
                    gw.warn(f"[OCPP:{charger_id}] Invalid or unsupported message format: {msg}")

        except WebSocketDisconnect:
            gw.info(f"[OCPP:{charger_id}] WebSocket disconnected")
        except Exception as e:
            gw.error(f"[OCPP:{charger_id}] WebSocket failure: {e}")
            gw.debug(traceback.format_exc())
        finally:
            _active_cons.pop(charger_id, None)

    return (app if not oapp else (oapp, app)) if _is_new_app else oapp


# GWAY Views for the main app. These are powered by bottle instead of FastAPI and run on another port.
# However, by being defined on the same project, data may be shared between both.
# These views only need to return html fragments and GWAY will render the rest of the needed content.
# However, they may also return a whole document or a bottle response directly if needed

def view_status():
    """
    /ocpp/status
    Return only the dashboard table fragment; GWAY will wrap this in its page chrome.
    """
    all_chargers = set(_active_cons) | set(_transactions)
    parts = ["<h1>OCPP Status Dashboard</h1>"]

    if not all_chargers:
        parts.append('<p><em>No chargers connected or transactions seen yet.</em></p>')
    else:
        parts.append('<table class="ocpp-status">')
        parts.append('<thead><tr>')
        for header in [
            "Charger ID", "Connected", "Txn ID", "Meter Start",
            "Latest", "kWh", "Status", "Actions"
        ]:
            parts.append(f'<th>{header}</th>')
        parts.append('</tr></thead><tbody>')

        for cid in sorted(all_chargers):
            ws_live = cid in _active_cons
            tx      = _transactions.get(cid)

            connected   = '🟢' if ws_live else '🔴'
            tx_id       = tx.get("transactionId") if tx else '-'
            meter_start = tx.get("meterStart")       if tx else '-'

            if tx:
                latest = (
                    tx.get("meterStop")
                    if tx.get("meterStop") is not None
                    else (tx["MeterValues"][-1].get("meter") if tx.get("MeterValues") else '-')
                )
                power  = power_consumed(tx)
                status = "Closed" if tx.get("syncStop") else "Open"
            else:
                latest = power = status = '-'

            parts.append('<tr>')
            for value in [cid, connected, tx_id, meter_start, latest, power, status]:
                parts.append(f'<td>{value}</td>')
            parts.append('<td>')
            parts.append(f'''
                <form action="/ocpp/action" method="post" class="inline">
                  <input type="hidden" name="charger_id" value="{cid}">
                  <select name="action">
                    <option value="remote_stop">Stop</option>
                    <option value="reset_soft">Soft Reset</option>
                    <option value="reset_hard">Hard Reset</option>
                    <option value="disconnect">Disconnect</option>
                  </select>
                  <button type="submit">Send</button>
                </form>
                <button type="button"
                  onclick="document.getElementById('details-{cid}').classList.toggle('hidden')">
                  Details
                </button>
            ''')
            parts.append('</td></tr>')
            parts.append(f'''
            <tr id="details-{cid}" class="hidden">
              <td colspan="8"><pre>{json.dumps(tx or {}, indent=2)}</pre></td>
            </tr>
            ''')

        parts.append('</tbody></table>')

    return "".join(parts)


# projects/ocpp.py

def extract_latest_meter(tx):
    """
    Return the latest Energy.Active.Import.Register (kWh) from MeterValues or meterStop.
    """
    if not tx:
        return "-"
    # Try meterStop first
    if tx.get("meterStop") is not None:
        try:
            return float(tx["meterStop"]) / 1000.0  # assume Wh, convert to kWh
        except Exception:
            return tx["meterStop"]
    # Try MeterValues: last entry, find Energy.Active.Import.Register
    mv = tx.get("MeterValues", [])
    if mv:
        last_mv = mv[-1]
        for sv in last_mv.get("sampledValue", []):
            if sv.get("measurand") == "Energy.Active.Import.Register":
                return sv.get("value")
    return "-"


def view_status():
    """
    /ocpp/status
    Return only the dashboard table fragment; GWAY will wrap this in its page chrome.
    """
    all_chargers = set(_active_cons) | set(_transactions)
    parts = ["<h1>OCPP Status Dashboard</h1>"]

    if not all_chargers:
        parts.append('<p><em>No chargers connected or transactions seen yet.</em></p>')
    else:
        parts.append('<table class="ocpp-status">')
        parts.append('<thead><tr>')
        for header in [
            "Charger ID", "Connected", "Txn ID", "Meter Start",
            "Latest (kWh)", "kWh Consumed", "Status", "Actions"
        ]:
            parts.append(f'<th>{header}</th>')
        parts.append('</tr></thead><tbody>')

        for cid in sorted(all_chargers):
            ws_live = cid in _active_cons
            tx      = _transactions.get(cid)

            connected   = '🟢' if ws_live else '🔴'
            tx_id       = tx.get("transactionId") if tx else '-'
            # Always show Meter Start in kWh if possible
            if tx and tx.get("meterStart") is not None:
                try:
                    meter_start = float(tx["meterStart"]) / 1000.0  # assume Wh, convert to kWh
                except Exception:
                    meter_start = tx.get("meterStart")
            else:
                meter_start = '-'

            if tx:
                latest = extract_latest_meter(tx)
                power  = power_consumed(tx)
                status = "Closed" if tx.get("syncStop") else "Open"
            else:
                latest = power = status = '-'

            parts.append('<tr>')
            for value in [cid, connected, tx_id, meter_start, latest, power, status]:
                parts.append(f'<td>{value}</td>')
            parts.append('<td>')
            parts.append(f'''
                <form action="/ocpp/action" method="post" class="inline">
                  <input type="hidden" name="charger_id" value="{cid}">
                  <select name="action">
                    <option value="remote_stop">Stop</option>
                    <option value="reset_soft">Soft Reset</option>
                    <option value="reset_hard">Hard Reset</option>
                    <option value="disconnect">Disconnect</option>
                  </select>
                  <button type="submit">Send</button>
                </form>
                <button type="button"
                  onclick="document.getElementById('details-{cid}').classList.toggle('hidden')">
                  Details
                </button>
            ''')
            parts.append('</td></tr>')
            parts.append(f'''
            <tr id="details-{cid}" class="hidden">
              <td colspan="8"><pre>{json.dumps(tx or {}, indent=2)}</pre></td>
            </tr>
            ''')

        parts.append('</tbody></table>')

    return "".join(parts)


def power_consumed(tx):
    """Calculate power consumed in kWh from transaction's meter values (Energy.Active.Import.Register)."""
    if not tx:
        return 0.0

    # Try to use MeterValues if present and well-formed
    meter_values = tx.get("MeterValues", [])
    energy_vals = []
    for entry in meter_values:
        # entry should be a dict with sampledValue: [...]
        for sv in entry.get("sampledValue", []):
            if sv.get("measurand") == "Energy.Active.Import.Register":
                val = sv.get("value")
                # Parse value as float (from string), handle missing
                try:
                    val_f = float(val)
                    if sv.get("unit") == "Wh":
                        val_f = val_f / 1000.0
                    # else assume kWh
                    energy_vals.append(val_f)
                except Exception:
                    pass

    if energy_vals:
        start = energy_vals[0]
        end = energy_vals[-1]
        return round(end - start, 3)

    # Fallback to meterStart/meterStop if no sampled values
    meter_start = tx.get("meterStart")
    meter_stop = tx.get("meterStop")
    # handle int or float or None
    try:
        if meter_start is not None and meter_stop is not None:
            return round(float(meter_stop) / 1000.0 - float(meter_start) / 1000.0, 3)
        if meter_start is not None:
            return 0.0  # no consumption measured
    except Exception:
        pass

    return 0.0
