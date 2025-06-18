# projects/ocpp.py

import json
import os
import time
import traceback
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from bottle import template
from typing import Dict
from gway import gw

_active_cons: Dict[str, WebSocket] = {}

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
    
transactions = {}  # charger_id -> dict

# TODO: Keep track of ongoing transactions so that they may be monitored real-time
#       Keep a tally of the power consumed and the latest SoC % of the EV and other connection info
#       Maybe we can piggy back off the per-txn logging we are doing

def setup_csms_v16_app(*,
        app=None,
        allowlist=None,
        denylist=None,  # New parameter for RFID denylist
        location=None,
        authorize=authorize_balance,
        records=None,
    ):
    """
    Minimal OCPP 1.6 CSMS implementation for conformance testing.
    Supports required Core actions, logs all requests, and accepts all.
    Optional RFID allowlist enables restricted access on Authorize.
    Optional denylist enables explicit denial even if present in allowlist.
    Optional `authorize` hook can be a callable or gw['name'].
    Optional `location` enables per-txn logging to work/etron/records/{location}/{charger}_{txn_id}.dat
    """
    global transactions
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
                            transactions[charger_id] = {
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
                            tx = transactions.pop(charger_id, None)
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
                            response_payload = {
                                "idTagInfo": {"status": "Accepted"}
                            }

                        elif action == "MeterValues":
                            tx = transactions.get(charger_id)
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


# Views for the main app. These will be used by the main bottle app when we do:
# web app setup - web server start-app

# File: projects/ocpp.py

def view_status():  # /ocpp/status
    """Simple dashboard listing the active CSMS connections and transactions."""
    status = []
    for charger_id, ws in _active_cons.items():
        tx = transactions.get(charger_id, {})
        conn_info = {
            "charger_id": charger_id,
            "connected": not ws.client_state.name == "DISCONNECTED",
            "transaction": tx.get("transactionId"),
            "meter_start": tx.get("meterStart"),
            "latest_meter": tx.get("MeterValues", [{}])[-1].get("timestampStr", "N/A"),
            "power_consumed": power_consumed(tx),
        }
        status.append(conn_info)

    return template("""
        <h2>OCPP Status Dashboard</h2>
        <table border="1">
            <tr><th>Charger ID</th><th>Connected</th><th>Transaction ID</th><th>Meter Start</th>
                <th>Latest Meter Reading</th><th>Power Consumed (kWh)</th></tr>
            % for conn in status:
                <tr>
                    <td>{{conn['charger_id']}}</td>
                    <td>{{conn['connected']}}</td>
                    <td>{{conn['transaction']}}</td>
                    <td>{{conn['meter_start']}}</td>
                    <td>{{conn['latest_meter']}}</td>
                    <td>{{conn['power_consumed']}}</td>
                </tr>
            % end
        </table>
    """, status=status)


def power_consumed(tx):
    """Calculate power consumed from transaction meter values."""
    if not tx or not tx.get("MeterValues"):
        return 0

    meter_start = tx.get("meterStart", 0)
    meter_values = tx["MeterValues"]
    meter_end = meter_values[-1].get("meter", meter_start)

    power_consumed_kWh = (meter_end - meter_start) / 1000  # assuming meter values are in Wh
    return round(power_consumed_kWh, 2)


# Test Client

# etron_client.py
import asyncio
import websockets
import json
import time
import random


async def simulate_evcs(
        host: str = "[WEBSITE_HOST|127.0.0.1]",
        ws_port: int = "[WEBSOCKET_PORT|9000]",
        rfid: str = "FFFFFFFF", 
        cp_path: str = "CPX"
    ):

    host = gw.resolve(host)
    ws_port = int(gw.resolve(ws_port))
    uri = f"ws://{host}:{ws_port}/{cp_path}"

    async with websockets.connect(uri, subprotocols=["ocpp1.6"]) as websocket:
        print("Connected to OCPP server.")

        # BootNotification
        boot_notification = [2, "boot", "BootNotification", {
            "chargePointModel": "Simulator",
            "chargePointVendor": "SimVendor"
        }]
        await websocket.send(json.dumps(boot_notification))
        await websocket.recv()

        # Authorize
        authorize_msg = [2, "auth", "Authorize", {"idTag": rfid}]
        await websocket.send(json.dumps(authorize_msg))
        await websocket.recv()

        # StartTransaction
        meter_start = random.randint(1000, 2000)
        transaction_msg = [2, "start", "StartTransaction", {
            "connectorId": 1,
            "idTag": rfid,
            "meterStart": meter_start
        }]
        await websocket.send(json.dumps(transaction_msg))
        response = await websocket.recv()
        transaction_id = json.loads(response)[2].get("transactionId")

        # Periodic MeterValues
        meter = meter_start
        for _ in range(10):
            meter += random.randint(50, 150)
            meter_values_msg = [2, "meter", "MeterValues", {
                "connectorId": 1,
                "transactionId": transaction_id,
                "meterValue": [{
                    "timestamp": time.strftime('%Y-%m-%dT%H:%M:%S') + "Z",
                    "sampledValue": [{"value": str(meter)}]
                }]
            }]
            await websocket.send(json.dumps(meter_values_msg))
            await asyncio.sleep(5)

        # StopTransaction
        stop_transaction_msg = [2, "stop", "StopTransaction", {
            "transactionId": transaction_id,
            "idTag": rfid,
            "meterStop": meter
        }]
        await websocket.send(json.dumps(stop_transaction_msg))
        await websocket.recv()

        print("Transaction simulation complete.")


