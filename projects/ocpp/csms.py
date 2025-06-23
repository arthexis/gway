
# file: projects/ocpp/csms.py

import json
import os
import time
import uuid
import traceback
import asyncio
from datetime import datetime
from fastapi import WebSocket, WebSocketDisconnect
from bottle import request, response, redirect, HTTPError
from typing import Dict, Optional
from gway import gw


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

# --- New: Track abnormal OCPP status notifications/errors here ---
_abnormal_status: Dict[str, dict] = {}  # charger_id → {"status": ..., "errorCode": ..., "info": ...}
# Only keep abnormal status; clear when charger sends "normal" (Available/NoError)


def is_abnormal_status(status: str, error_code: str) -> bool:
    """Determine if a status/errorCode is 'abnormal' per OCPP 1.6."""
    status = (status or "").capitalize()
    error_code = (error_code or "").capitalize()
    # Available/NoError or Preparing are 'normal'
    if status in ("Available", "Preparing") and error_code in ("Noerror", "", None):
        return False
    # All Faulted, Unavailable, Suspended, etc. are abnormal
    if status in ("Faulted", "Unavailable", "Suspendedev", "Suspended", "Removed"):
        return True
    if error_code not in ("Noerror", "", None):
        return True
    return False


def setup_app(*,
    app=None,
    allowlist=None,
    denylist=None,
    location=None,
    authorize=authorize_balance,
    email=None,
):
    global _transactions, _active_cons, _abnormal_status
    email = email if isinstance(email, str) else gw.resolve('[ADMIN_EMAIL]')

    oapp = app
    from fastapi import FastAPI as _FastAPI
    if (_is_new_app := not (app := gw.unwrap_one(app, _FastAPI))):
        app = _FastAPI()

    validator = None
    if isinstance(authorize, str):
        validator = gw[authorize]
    elif callable(authorize):
        validator = authorize

    def is_authorized_rfid(rfid: str) -> bool:
        if denylist and gw.cdv.validate(denylist, rfid):
            gw.info(f"[OCPP] RFID {rfid!r} is present in denylist. Authorization denied.")
            return False
        if not allowlist:
            gw.warn("[OCPP] No RFID allowlist configured — rejecting all authorization requests.")
            return False
        return gw.cdv.validate(allowlist, rfid, validator=validator)

    @app.websocket("/{path:path}")
    async def websocket_ocpp(websocket: WebSocket, path: str):
        global _csms_loop, _abnormal_status
        _csms_loop = asyncio.get_running_loop()

        charger_id = path.strip("/").split("/")[-1]
        gw.info(f"[OCPP] WebSocket connected: charger_id={charger_id}")

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

                        if email:
                            subject = f"OCPP: Charger {charger_id} STARTED transaction {transaction_id}"
                            body = (
                                f"Charging session started.\n"
                                f"Charger: {charger_id}\n"
                                f"idTag: {payload.get('idTag')}\n"
                                f"Connector: {payload.get('connectorId')}\n"
                                f"Start Time: {datetime.utcfromtimestamp(now).isoformat()}Z\n"
                                f"Transaction ID: {transaction_id}\n"
                                f"Meter Start: {payload.get('meterStart')}\n"
                                f"Reservation ID: {payload.get('reservationId', -1)}"
                            )
                            gw.mail.send(subject, body, to=email)

                    elif action == "MeterValues":
                        tx = _transactions.get(charger_id)
                        if tx:
                            for entry in payload.get("meterValue", []):
                                ts = entry.get("timestamp")
                                ts_epoch = (
                                    int(datetime.fromisoformat(ts.rstrip("Z")).timestamp())
                                    if ts else int(time.time())
                                )
                                sampled = []
                                for sv in entry.get("sampledValue", []):
                                    val = sv.get("value")
                                    unit = sv.get("unit", "")
                                    measurand = sv.get("measurand", "")
                                    try:
                                        fval = float(val)
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
                        status = payload.get("status")
                        error_code = payload.get("errorCode")
                        info = payload.get("info", "")
                        # Only store if abnormal; remove if cleared
                        if is_abnormal_status(status, error_code):
                            _abnormal_status[charger_id] = {
                                "status": status,
                                "errorCode": error_code,
                                "info": info,
                                "timestamp": datetime.utcnow().isoformat() + "Z"
                            }
                            gw.warn(f"[OCPP] Abnormal status for {charger_id}: {status}/{error_code} - {info}")
                        else:
                            if charger_id in _abnormal_status:
                                gw.info(f"[OCPP] Status normalized for {charger_id}: {status}/{error_code}")
                                _abnormal_status.pop(charger_id, None)
                        response_payload = {}

                    else:
                        response_payload = {"status": "Accepted"}

                    response = [3, message_id, response_payload]
                    gw.info(f"[OCPP:{charger_id}] ← {action} => {response_payload}")
                    await websocket.send_text(json.dumps(response))

                elif isinstance(msg, list) and msg[0] == 3:
                    gw.debug(f"[OCPP:{charger_id}] Received CALLRESULT: {msg}")
                    continue

                elif isinstance(msg, list) and msg[0] == 4:
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



def dispatch_action(charger_id: str, action: str):
    """
    Dispatch a remote admin action to the charger over OCPP via websocket.
    """
    ws = _active_cons.get(charger_id)
    if not ws:
        raise HTTPError(404, "No active connection")
    msg_id = str(uuid.uuid4())

    # Compose and send the appropriate OCPP message for the requested action
    if action == "remote_stop":
        tx = _transactions.get(charger_id)
        if not tx:
            raise HTTPError(404, "No transaction to stop")
        coro = ws.send_text(json.dumps([2, msg_id, "RemoteStopTransaction",
                                        {"transactionId": tx["transactionId"]}]))
    elif action.startswith("reset_"):
        _, mode = action.split("_", 1)
        coro = ws.send_text(json.dumps([2, msg_id, "Reset", {"type": mode.capitalize()}]))
    elif action == "disconnect":
        coro = ws.close(code=1000, reason="Admin disconnect")
    else:
        raise HTTPError(400, f"Unknown action: {action}")

    if _csms_loop:
        _csms_loop.call_soon_threadsafe(lambda: _csms_loop.create_task(coro))
    else:
        gw.warn("No CSMS event loop; action not sent")

    return {"status": "requested", "messageId": msg_id}


def view_charger_status(*, action=None, charger_id=None, **_):
    """
    /ocpp/charger-status
    Handles GET and POST for dashboard. On POST with action, dispatch and redirect to clear state.
    """
    if request.method == "POST":
        action = request.forms.get("action")
        charger_id = request.forms.get("charger_id")
        if action and charger_id:
            try:
                dispatch_action(charger_id, action)
            except Exception as e:
                gw.error(f"Failed to dispatch action {action} to {charger_id}: {e}")
            # PRG: Redirect to clear POST
            return redirect(request.fullpath or "/ocpp/charger-status")
        # If POST but missing data, just fall through and re-render

    all_chargers = set(_active_cons) | set(_transactions)
    parts = ["<h1>OCPP Status Dashboard</h1>"]

    # --- Show current abnormal statuses/errors, if any ---
    if _abnormal_status:
        parts.append(
            '<div style="color:#fff;background:#b22;padding:12px;font-weight:bold;margin-bottom:12px">'
            "⚠️ Abnormal Charger Status Detected:<ul style='margin:0'>"
        )
        for cid, err in sorted(_abnormal_status.items()):
            status = err.get("status", "")
            error_code = err.get("errorCode", "")
            info = err.get("info", "")
            ts = err.get("timestamp", "")
            msg = f"<b>{cid}</b>: {status}/{error_code}"
            if info:
                msg += f" ({info})"
            if ts:
                msg += f" <span style='font-size:0.9em;color:#eee'>@{ts}</span>"
            parts.append(f"<li>{msg}</li>")
        parts.append("</ul></div>")

    if not all_chargers:
        parts.append('<p><em>No chargers connected or transactions seen yet.</em></p>')
    else:
        parts.append('<form method="post" action="" id="ocpp-action-form"></form>')
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
            # Updated form: each row form POSTs to this view (action="")
            parts.append(f'''
                <form method="post" action="" style="display:inline">
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


def extract_meter(tx):
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



    """
    /ocpp/action
    Single‐endpoint dispatcher for all dropdown actions.
    """
    ws = _active_cons.get(charger_id)
    if not ws:
        raise HTTPError(404, "No active connection")
    msg_id = str(uuid.uuid4())

    # build the right OCPP message
    if action == "remote_stop":
        tx = _transactions.get(charger_id)
        if not tx:
            raise HTTPError(404, "No transaction to stop")
        coro = ws.send_text(json.dumps([2, msg_id, "RemoteStopTransaction",
                                        {"transactionId": tx["transactionId"]}]))

    elif action.startswith("change_availability_"):
        _, _, mode = action.partition("_availability_")
        coro = ws.send_text(json.dumps([2, msg_id, "ChangeAvailability",
                                        {"connectorId": 0, "type": mode.capitalize()}]))

    elif action.startswith("reset_"):
        _, mode = action.split("_", 1)
        coro = ws.send_text(json.dumps([2, msg_id, "Reset", {"type": mode.capitalize()}]))

    elif action == "disconnect":
        # schedule a raw close
        coro = ws.close(code=1000, reason="Admin disconnect")

    else:
        raise HTTPError(400, f"Unknown action: {action}")

    if _csms_loop:
        # schedule it on the FastAPI loopMore actions
        _csms_loop.call_soon_threadsafe(lambda: _csms_loop.create_task(coro))
    else:
        gw.warn("No CSMS event loop; action not sent")

    return {"status": "requested", "messageId": msg_id}