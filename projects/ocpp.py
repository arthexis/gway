# projects/ocpp.py

import json
import os
import time
import uuid
import traceback
import asyncio
import websockets
import random
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from bottle import template, HTTPError
from typing import Dict, Optional
from gway import gw


# Both setup_sink_app and setup_csms_app support receiving an app argument
# which may be a single app or a collection of apps, similar to web.app.setup

# Bottle does not support websockets properly, so we need to use FastAPI for OCPP. 
# However we still use Bottle for the user interface (see view section down below)

def setup_sink_app(*, app=None):
    """
    Basic OCPP passive sink for messages, acting as a dummy CSMS server.
    This won't pass compliance or provide authentication. It just accepts and logs all.
    Note: This version of the app was tested at the EVCS with real EVs.
    """
    # A - This line ensures we find just the kind of app we need or create one if missing
    if (_is_new_app := not (app := gw.unwrap_one((oapp := app), FastAPI))):
        app = FastAPI()

    @app.websocket("{path:path}")
    async def websocket_ocpp(websocket: WebSocket, path: str):
        gw.info(f"[OCPP] New WebSocket connection at /{path}")
        try:
            await websocket.accept()
            while True:
                raw = await websocket.receive_text()
                gw.info(f"[OCPP:{path}] Message received:", raw)

                try:
                    msg = json.loads(raw)
                    if isinstance(msg, list) and len(msg) >= 3 and msg[0] == 2:
                        message_id = msg[1]
                        action = msg[2]
                        payload = msg[3] if len(msg) > 3 else {}

                        gw.info(f"[OCPP:{path}] -> Action: {action} | Payload: {payload}")
                        response = [3, message_id, {"status": "Accepted"}]
                        await websocket.send_text(json.dumps(response))
                        gw.info(f"[OCPP:{path}] <- Acknowledged: {response}")
                    else:
                        gw.warning(f"[OCPP:{path}] Received non-Call message or malformed")
                except Exception as e:
                    gw.error(f"[OCPP:{path}] Error parsing message: {e}")
                    gw.debug(traceback.format_exc())

        except WebSocketDisconnect:
            gw.info(f"[OCPP:{path}] Disconnected")
        except Exception as e:
            gw.error(f"[OCPP:{path}] WebSocket error: {e}")
            gw.debug(traceback.format_exc())

    # B- This return pattern ensures we include our app in the bundle (if any)
    if _is_new_app:
        return app if not oapp else (oapp, app)    
    return oapp

...


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


def setup_csms_v16_app(*,
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

    oapp = app
    if (_is_new_app := not (app := gw.unwrap_one(app, FastAPI))):
        app = FastAPI()

    # Compose the validator: prefer explicit callable, then gw[] ref, else default (balance >= 1)
    validator = None
    if isinstance(authorize, str):
        validator = gw[authorize]
    elif callable(authorize):
        validator = authorize

    # Always check against latest file (never cache), and warn if allowlist missing
    def is_authorized_rfid(rfid: str) -> bool:
        # --- DENYLIST logic ---
        if denylist:
            if gw.cdv.validate(denylist, rfid):
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

        requested_protocols = websocket.headers.get("sec-websocket-protocol", "")
        requested_protocols = [p.strip() for p in requested_protocols.split(",") if p.strip()]

        try:
            if "ocpp1.6" in requested_protocols:
                await websocket.accept(subprotocol="ocpp1.6")
            else:
                await websocket.accept()

            _active_cons[charger_id] = websocket

            while True:
                raw = await websocket.receive_text()
                gw.info(f"[OCPP:{charger_id}] → {raw}")

                try:
                    try:
                        msg = json.loads(raw)
                    except json.JSONDecodeError:
                        gw.warn(f"[OCPP:{charger_id}] Received non-JSON message: {raw!r}")
                        continue

                    if isinstance(msg, list) and msg[0] == 2:
                        message_id = msg[1]
                        action = msg[2]
                        payload = msg[3] if len(msg) > 3 else {}
                        gw.debug(f"[OCPP:{charger_id}] Action={action} Payload={payload}")

                        response_payload = {}

                        if action == "Authorize":
                            id_tag = payload.get("idTag")
                            status = "Accepted" if is_authorized_rfid(id_tag) else "Rejected"
                            response_payload = {"idTagInfo": {"status": status}}

                        elif action == "BootNotification":
                            response_payload = {
                                "currentTime": datetime.utcnow().isoformat() + "Z",
                                "interval": 300,
                                "status": "Accepted"
                            }

                        elif action == "Heartbeat":
                            response_payload = {
                                "currentTime": datetime.utcnow().isoformat() + "Z"
                            }

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
                                    file_path = gw.resource("work", "etron", "records", location,
                                                            f"{charger_id}_{tx['transactionId']}.dat")
                                    os.makedirs(os.path.dirname(file_path), exist_ok=True)
                                    with open(file_path, "w") as f:
                                        json.dump(tx, f, indent=2)
                            response_payload = {"idTagInfo": {"status": "Accepted"}}


                        elif action == "MeterValues":
                            tx = _transactions.get(charger_id)
                            if tx:
                                entries = payload.get("meterValue", [])
                                for entry in entries:
                                    ts = entry.get("timestamp")
                                    ts_epoch = int(datetime.fromisoformat(
                                        ts.rstrip("Z")).timestamp()) if ts else int(time.time())
                                    sample = {
                                        "syncMeter": 1,
                                        "timestamp": ts_epoch,
                                        "timestampStr": datetime.utcfromtimestamp(ts_epoch).isoformat() + "Z",
                                        "timeMs": int(time.time() * 1000) % 1000,
                                    }
                                    tx["MeterValues"].append(sample)
                            response_payload = {}

                        elif action == "StatusNotification":
                            response_payload = {}

                        else:
                            response_payload = {"status": "Accepted"}

                        response = [3, message_id, response_payload]
                        gw.info(f"[OCPP:{charger_id}] ← {action} => {response_payload}")
                        await websocket.send_text(json.dumps(response))

                    else:
                        gw.warn(f"[OCPP:{charger_id}] Invalid or unsupported message format: {msg}")

                except Exception as e:
                    gw.error(f"[OCPP:{charger_id}] Message processing error: {e}")
                    gw.debug(traceback.format_exc())

        except WebSocketDisconnect:
            gw.info(f"[OCPP:{charger_id}] WebSocket disconnected")
        except Exception as e:
            gw.error(f"[OCPP:{charger_id}] WebSocket failure: {e}")
            gw.debug(traceback.format_exc())
        finally:
            _active_cons.pop(charger_id, None)

    return (app if not oapp else (oapp, app)) if _is_new_app else oapp


setup_csms_app = setup_csms_v16_app


# Views for the main app. These are powered by bottle instead of FastAPI and run on another port.
# However, by being defined on the same project, data may be shared between both.

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
                    <option value="change_availability_unavailable">Off</option>
                    <option value="change_availability_available">On</option>
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

def view_action(charger_id: str, action: str):
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
        # schedule it on the FastAPI loop
        _csms_loop.call_soon_threadsafe(lambda: _csms_loop.create_task(coro))
    else:
        gw.warn("No CSMS event loop; action not sent")

    return {"status": "requested", "messageId": msg_id}

...


def power_consumed(tx):
    """Calculate power consumed from transaction meter values."""
    if not tx or not tx.get("MeterValues"):
        return 0

    meter_start = tx.get("meterStart", 0)
    meter_values = tx["MeterValues"]
    meter_end = meter_values[-1].get("meter", meter_start)

    power_consumed_kWh = (meter_end - meter_start) / 1000  # assuming meter values are in Wh
    return round(power_consumed_kWh, 2)

...

async def simulate_evcs(*,
        host: str = "[WEBSITE_HOST|127.0.0.1]",
        ws_port: int = "[WEBSOCKET_PORT|9000]",
        rfid: str = "FFFFFFFF",
        cp_path: str = "CPX",
        duration: int = 60,
        repeat: bool = False,
    ):
    """
    Simulate an EVCS connecting and running a charging session.
    Listens & logs all CSMS→CP messages, and respects RemoteStopTransaction.
    """
    import asyncio, json, random, time, websockets
    from gway import gw

    host    = gw.resolve(host)
    ws_port = int(gw.resolve(ws_port))
    uri     = f"ws://{host}:{ws_port}/{cp_path}"

    while True:
        # Will signal if CSMS asked us to stop
        stop_event = asyncio.Event()

        async with websockets.connect(uri, subprotocols=["ocpp1.6"]) as ws:
            print(f"[Simulator] Connected to {uri}")

            # ─── listener ─────────────────────────────────────────────
            async def listen_to_csms():
                try:
                    while True:
                        raw = await ws.recv()
                        print(f"[Simulator ← CSMS] {raw}")
                        try:
                            msg = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        # always confirm CALLs
                        if isinstance(msg, list) and msg[0] == 2:
                            msg_id, action, payload = msg[1], msg[2], (msg[3] if len(msg)>3 else {})
                            # send empty Confirmation
                            await ws.send(json.dumps([3, msg_id, {}]))
                            if action == "RemoteStopTransaction":
                                print("[Simulator] Received RemoteStopTransaction → stopping now")
                                stop_event.set()
                except websockets.ConnectionClosed:
                    pass

            listener = asyncio.create_task(listen_to_csms())

            # ─── boot & authorize ─────────────────────────────────────
            bn = [2, "boot", "BootNotification",
                  {"chargePointModel":"Simulator","chargePointVendor":"SimVendor"}]
            await ws.send(json.dumps(bn))
            await ws.recv()

            auth = [2, "auth", "Authorize", {"idTag": rfid}]
            await ws.send(json.dumps(auth))
            await ws.recv()

            # ─── start transaction ────────────────────────────────────
            meter_start = random.randint(1000, 2000)
            st = [2, "start", "StartTransaction",
                  {"connectorId":1, "idTag":rfid, "meterStart":meter_start}]
            await ws.send(json.dumps(st))
            resp = await ws.recv()
            tx_id = json.loads(resp)[2]["transactionId"]

            print(f"[Simulator] Transaction {tx_id} started at meter {meter_start}")

            # ─── meter loop ───────────────────────────────────────────
            actual_duration = random.uniform(duration*0.75, duration*1.25)
            interval = actual_duration / 10
            meter = meter_start

            for _ in range(10):
                if stop_event.is_set():
                    print("[Simulator] Stop event triggered—breaking meter loop")
                    break
                meter += random.randint(50,150)
                mv = [2, "meter", "MeterValues", {
                    "connectorId":1,
                    "transactionId":tx_id,
                    "meterValue":[
                        {"timestamp": time.strftime('%Y-%m-%dT%H:%M:%S')+"Z",
                         "sampledValue":[{"value":str(meter)}]}
                    ]
                }]
                await ws.send(json.dumps(mv))
                await asyncio.sleep(interval)

            # ─── stop transaction ─────────────────────────────────────
            # either natural end or forced
            stop = [2, "stop", "StopTransaction",
                    {"transactionId":tx_id, "idTag":rfid, "meterStop":meter}]
            await ws.send(json.dumps(stop))
            await ws.recv()
            print(f"[Simulator] Transaction {tx_id} stopped at meter {meter}")

            # clean up
            listener.cancel()
            try: await listener
            except: pass

        if not repeat:
            break

        print(f"[Simulator] Waiting {actual_duration:.1f}s before next cycle")
        await asyncio.sleep(actual_duration)
