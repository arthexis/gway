# file: projects/ocpp/csms.py
# web.app path: ocpp/csms/

import json
import os
import time
import uuid
import traceback
import asyncio
from datetime import datetime
from fastapi import WebSocket, WebSocketDisconnect
from bottle import request, redirect, HTTPError
from typing import Dict, Optional
from gway import gw

_csms_loop: Optional[asyncio.AbstractEventLoop] = None
_transactions: Dict[str, dict] = {}           # charger_id → latest transaction
_active_cons: Dict[str, WebSocket] = {}      # charger_id → live WebSocket
_latest_heartbeat: Dict[str, str] = {}  # charger_id → ISO8601 UTC time string
_abnormal_status: Dict[str, dict] = {}  # charger_id → {"status": ..., "errorCode": ..., "info": ...}

def authorize_balance(**record):
    """
    Default OCPP RFID secondary validator: Only authorize if balance >= 1.
    The RFID needs to exist already for this to be called in the first place.
    """
    try:
        return float(record.get("balance", "0")) >= 1
    except Exception:
        return False
    
def setup_app(*,
    app=None,
    allowlist=None,
    denylist=None,
    location=None,
    authorize=authorize_balance,
    email=None,
    auth_required=False,
):
    global _transactions, _active_cons, _abnormal_status
    email = email if isinstance(email, str) else (gw.resolve('[ADMIN_EMAIL]') if email else email)

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
        if auth_required:
            if not gw.web.auth.check_websocket_auth(websocket):
                await websocket.close(code=4401, reason="Unauthorized")
                gw.warn(f"[OCPP] Unauthorized WebSocket connection attempt for charger_id={path}")
                return

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
                            if tx.get("MeterValues"):
                                try:
                                    archive_e(charger_id, tx["transactionId"], tx["MeterValues"])
                                except Exception as e:
                                    gw.error("Error recording energy chart.")
                                    gw.exception(e)
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
                    # Handle CALLRESULT, check for Heartbeat ACK to record latest heartbeat time
                    payload = msg[2] if len(msg) > 2 else {}
                    if isinstance(payload, dict) and "currentTime" in payload:
                        # Only update for Heartbeat (or any other call with currentTime)
                        _latest_heartbeat[charger_id] = payload["currentTime"]
                        gw.debug(f"[OCPP:{charger_id}] Updated latest heartbeat to {_latest_heartbeat[charger_id]}")
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

# Bottle-based views are used for the interface, params injected by GWAY from query/payload
# GWAY allows us to have the WS FastAPI server and Bottle UI server share memory space,
# simply by placing both functions in the same project file.

# TODO: <Details> no longer works properly, clicking the button stretches the card box vertically
#       for a second and the log flashes on screen before closing and going back to not showing.

# TODO: The graph link doesn't take us anywhere, screen stays the same after clicking.

def view_charger_status(*, action=None, charger_id=None, **_):
    """
    Card-based OCPP dashboard: summary of all charger connections.
    """
    if request.method == "POST":
        action = request.forms.get("action")
        charger_id = request.forms.get("charger_id")
        if action and charger_id:
            try:
                dispatch_action(charger_id, action)
            except Exception as e:
                gw.error(f"Failed to dispatch action {action} to {charger_id}: {e}")
            return redirect(request.fullpath or "/ocpp/charger-status")

    all_chargers = set(_active_cons) | set(_transactions)
    html = ["<h1>OCPP Status Dashboard</h1>"]

    # --- Show abnormal statuses if present ---
    if _abnormal_status:
        html.append(
            '<div style="color:#fff;background:#b22;padding:12px;font-weight:bold;margin-bottom:18px">'
            "⚠️ Abnormal Charger Status Detected:<ul style='margin:0'>"
        )
        for cid, err in sorted(_abnormal_status.items()):
            status = err.get("status", "")
            error_code = err.get("errorCode", "")
            info = err.get("info", "")
            ts = err.get("timestamp", "")
            msg = f"<b>{cid}</b>: {status}/{error_code}"
            if info: msg += f" ({info})"
            if ts: msg += f" <span style='font-size:0.9em;color:#eee'>@{ts}</span>"
            html.append(f"<li>{msg}</li>")
        html.append("</ul></div>")

    if not all_chargers:
        html.append('<p><em>No chargers connected or transactions seen yet.</em></p>')
    else:
        html.append('<div class="ocpp-dashboard">')
        for cid in sorted(all_chargers):
            ws_live = cid in _active_cons
            tx      = _transactions.get(cid)
            connected   = '🟢' if ws_live else '🔴'
            tx_id       = tx.get("transactionId") if tx else '-'
            meter_start = tx.get("meterStart")       if tx else '-'
            latest      = (
                tx.get("meterStop")
                if tx and tx.get("meterStop") is not None
                else (tx["MeterValues"][-1].get("meter") if tx and tx.get("MeterValues") else 'None')
            )
            power  = power_consumed(tx)
            status = "Closed" if tx and tx.get("syncStop") else "Open" if tx else '-'
            # Heartbeat
            raw_hb = _latest_heartbeat.get(cid)
            if raw_hb:
                try:
                    from datetime import datetime, timezone
                    dt = datetime.fromisoformat(raw_hb.replace("Z", "+00:00")).astimezone()
                    latest_hb = dt.strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    latest_hb = raw_hb
            else:
                latest_hb = "-"

            html.append('<div class="charger-card">')
            html.append(f'''
                <div class="charger-header">
                    <span class="charger-id">{cid}</span>
                    <span class="charger-status">{connected}</span>
                </div>
                <div class="charger-details-row">
                    <label>Txn ID:</label> <span>{tx_id}</span>
                    <label>Start:</label> <span>{meter_start}</span>
                    <label>Latest:</label> <span>{latest}</span>
                </div>
                <div class="charger-details-row">
                    <label>kWh:</label> <span>{power}</span>
                    <label>Status:</label> <span>{status}</span>
                    <label>Last HB:</label> <span>{latest_hb}</span>
                </div>
                <form method="post" action="" class="charger-action-row">
                    <input type="hidden" name="charger_id" value="{cid}">
                    <select name="action" id="action-{cid}" aria-label="Action">
                        <option value="remote_stop">Stop</option>
                        <option value="reset_soft">Soft Reset</option>
                        <option value="reset_hard">Hard Reset</option>
                        <option value="disconnect">Disconnect</option>
                    </select>
                    <button type="submit" name="do" value="send">Send</button>
                    <button type="submit" name="do" value="details" class="details-btn" data-target="details-{cid}">Details</button>
                    <button type="submit" name="do" value="graph" class="graph-btn">Graph</button>
                </form>
                <div id="details-{cid}" class="charger-details-panel hidden">
                    <pre>{json.dumps(tx or {}, indent=2)}</pre>
                </div>
            ''')
            html.append('</div>')
        html.append('</div>')  # end .ocpp-dashboard

    # WebSocket URL bar
    ws_url = gw.web.build_ws_url()
    html.append(f"""
    <div class="ocpp-wsbar">
      <input type="text" id="ocpp-ws-url" value="{ws_url}" readonly
        style="flex:1;font-family:monospace;font-size:1em;
               padding:10px 6px;background:#222;color:#fff;
               border:1px solid #333;border-radius:5px;min-width:160px;max-width:530px;"/>
      <button id="copy-ws-url-btn"
        style="padding:6px 16px;font-size:1em;border-radius:5px;
               border:1px solid #444;background:#444;color:#fff;cursor:pointer">
        Copy
      </button>
    </div>
    """)

    # TODO: This next link should ideally be placed on the right column, right to the 
    #       box with the ocpp link and copy button. If there is no existing CSS to do this
    #       create a separate block of css that we can add to our static data.

    if gw.web.app.is_setup('ocpp.evcs'):
        html.append("""
        <div>
            <a href="/ocpp/evcs/cp-simulator">Activate or visualize the online simulator.</a>
        </div>
        """)
    return "".join(html)


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

...

# Calculation tools

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


def archive_e(charger_id, transaction_id, meter_values):
    """
    Store MeterValues for a charger/transaction as a dated file for graphing.
    """
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    base = gw.resource("work", "etron", "graphs", charger_id)
    os.makedirs(base, exist_ok=True)
    # File name: <date>_<txn_id>.json (add .json for safety)
    file_path = os.path.join(base, f"{date_str}_{transaction_id}.json")
    with open(file_path, "w") as f:
        json.dump(meter_values, f, indent=2)
    return file_path


def view_energy_graph(*, charger_id=None, date=None, **_):
    """
    Render a page with a graph for a charger's session by date.
    """
    import glob
    from datetime import datetime
    html = ['<link rel="stylesheet" href="/static/styles/charger_status.css">']
    html.append('<h1>Charger Transaction Graph</h1>')

    # Form for charger/date selector
    graph_dir = gw.resource("work", "etron", "graphs")
    charger_dirs = sorted(os.listdir(graph_dir)) if os.path.isdir(graph_dir) else []
    txn_files = []
    if charger_id:
        cdir = os.path.join(graph_dir, charger_id)
        if os.path.isdir(cdir):
            txn_files = sorted(glob.glob(os.path.join(cdir, "*.json")))
    html.append('<form method="get" action="/ocpp/csms/energy-graph" style="margin-bottom:2em;">')
    html.append('<label>Charger: <select name="charger_id">')
    html.append('<option value="">(choose)</option>')
    for cid in charger_dirs:
        sel = ' selected' if cid == charger_id else ''
        html.append(f'<option value="{cid}"{sel}>{cid}</option>')
    html.append('</select></label> ')
    if txn_files:
        html.append('<label>Transaction Date: <select name="date">')
        html.append('<option value="">(choose)</option>')
        for fn in txn_files:
            # Filename: YYYY-MM-DD_<txn_id>.json
            dt = os.path.basename(fn).split("_")[0]
            sel = ' selected' if dt == date else ''
            html.append(f'<option value="{dt}"{sel}>{dt}</option>')
        html.append('</select></label> ')
    html.append('<button type="submit">Show</button></form>')

    # Load and render the graph if possible
    graph_data = []
    if charger_id and date:
        base = os.path.join(graph_dir, charger_id)
        match = glob.glob(os.path.join(base, f"{date}_*.json"))
        if match:
            with open(match[0]) as f:
                graph_data = json.load(f)
        # Graph placeholder: (replace with your JS plotting lib)
        html.append('<div style="background:#222;border-radius:1em;padding:1.5em;min-height:320px;">')
        if graph_data:
            html.append('<h3>Session kWh Over Time</h3>')
            html.append('<pre style="color:#fff;font-size:1.02em;">')
            # Show simple table (replace with a chart)
            html.append("Time                | kWh\n---------------------|------\n")
            for mv in graph_data:
                ts = mv.get("timestampStr", "-")
                kwh = "-"
                for sv in mv.get("sampledValue", []):
                    if sv.get("measurand") == "Energy.Active.Import.Register":
                        kwh = sv.get("value")
                html.append(f"{ts:21} | {kwh}\n")
            html.append('</pre>')
        else:
            html.append("<em>No data available for this session.</em>")
        html.append('</div>')

    return "".join(html)
