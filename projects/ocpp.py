# projects/ocpp.py

import json
import os
import time
import traceback
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from typing import Dict
from gway import gw

_active_cons: Dict[str, WebSocket] = {}

# Both setup_sink_app and setup_csms_app support receiving an app argument
# which may be a single app or a collection of apps. 

# Bottle does not support websockets properly, so we need to use FastAPI for OCPP. 
# However we still use Bottle for the user interface (see view section down below)

def setup_sink_app(*, 
        app=None,
        host='[OCPP_CSMS_HOST|0.0.0.0]', 
        port='[OCPP_CSMS_PORT|9000]',
        base="",
    ):
    """
    Basic OCPP passive sink for messages, acting as a dummy CSMS server.
    This won't pass compliance or provide authentication. It just accepts and logs all.
    Note: This version of the app was tested at the EVCS with real EVs.
    """


    # A - This line ensures we find just the kind of app we need or create one if missing
    if (_is_new_app := not (app := gw.unwrap_one((oapp := app), FastAPI))):
        app = FastAPI()

    @app.websocket(f"{base}/"+"{path:path}")
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

    gw.info(f"Setup passive OCPP sink directly on {host}:{port}/{base}")

    # B- This return pattern ensures we include our app in the bundle (if any)
    if _is_new_app:
        return app if not oapp else (oapp, app)    
    return oapp


def setup_csms_v01_app(*, 
        app=None, 
        host='[OCPP_CSMS_HOST|0.0.0.0]', 
        port='[OCPP_CSMS_PORT|9000]', 
        allowlist=None,
    ):
    """
    OCPP 1.6 CSMS implementation with RFID authorization.
    Specify an allowlist file in .cdv format (RFID: [extra fields...])
    Note: This version of the app was tested at the EVCS with real EVs.
    """
    # A - This block ensures we find just the kind of app we need or create one if missing
    oapp = app
    if (_is_new_app := not (app := gw.unwrap_one(app, FastAPI))):
        app = FastAPI()

    def load_allowlist() -> dict[str, list[str]]:
        if not allowlist:
            return {}

        try:
            path = gw.resource(allowlist)
            if not os.path.exists(path):
                gw.error(f"[OCPP] Allowlist file not found: {path}")
                return {}

            result = {}
            with open(path, "r") as f:
                for lineno, line in enumerate(f, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split(":")
                    rfid = parts[0].strip()

                    if len(rfid) == 8 and all(c in "0123456789ABCDEFabcdef" for c in rfid):
                        extra_fields = [part.strip() for part in parts[1:]]
                        result[rfid] = extra_fields
                    else:
                        gw.warn(f"[OCPP] Invalid RFID at line {lineno} in allowlist: '{line}'")

            return result

        except Exception as e:
            gw.abort(f"[OCPP] Failed to read allowlist '{allowlist}': {e}")

    def is_authorized_rfid(rfid: str) -> bool:
        if not allowlist:
            return True
        return rfid in load_allowlist()

    @app.websocket("/{path:path}")
    async def websocket_ocpp(websocket: WebSocket, path: str):
        charger_id = path.strip("/").split("/")[-1]
        gw.info(f"[OCPP] New WebSocket connection at /{path} (charger_id={charger_id})")
        try:
            await websocket.accept()
            _active_cons[charger_id] = websocket

            while True:
                raw = await websocket.receive_text()
                gw.info(f"[OCPP:{charger_id}] Message received: {raw}")

                try:
                    msg = json.loads(raw)
                    if isinstance(msg, list) and len(msg) >= 3 and msg[0] == 2:
                        message_id = msg[1]
                        action = msg[2]
                        payload = msg[3] if len(msg) > 3 else {}

                        gw.info(f"[OCPP:{charger_id}] -> Action: {action} | Payload: {payload}")

                        if action == "Authorize":
                            id_tag = payload.get("idTag")
                            accepted = is_authorized_rfid(id_tag)
                            status = "Accepted" if accepted else "Rejected"
                            response = [3, message_id, {"idTagInfo": {"status": status}}]
                            gw.info(f"[OCPP:{charger_id}] <- Authorize: {id_tag} -> {status}")
                        else:
                            response = [3, message_id, {"status": "Accepted"}]
                            gw.info(f"[OCPP:{charger_id}] <- Acknowledged {action}: {response}")

                        await websocket.send_text(json.dumps(response))
                    else:
                        gw.warning(f"[OCPP:{charger_id}] Received non-Call message or malformed")

                except Exception as e:
                    gw.error(f"[OCPP:{charger_id}] Error parsing message: {e}")
                    gw.debug(traceback.format_exc())

        except WebSocketDisconnect:
            gw.info(f"[OCPP:{charger_id}] Disconnected")
        except Exception as e:
            gw.error(f"[OCPP:{charger_id}] WebSocket error: {e}")
            gw.debug(traceback.format_exc())
        finally:
            _active_cons.pop(charger_id, None)

        if allowlist:
            _ = load_allowlist()  # Validates on startup
            gw.debug("Allowlist loaded without errors.")

        gw.info(f"Setup OCPP 1.6 auth sink on {host}:{port} (allowlist={allowlist})")
    
    # B- This return pattern ensures we include our app in the bundle (if any)
    return (app if not oapp else (oapp, app)) if _is_new_app else oapp


...


# OCPP Compliant v1.6 Prototype

def setup_csms_v16_app(*, 
        app=None, 
        allowlist=None,
        authlist=None,
    ):
    """
    Minimal OCPP 1.6 CSMS implementation for conformance testing.
    Supports required Core actions, logs all requests, and accepts all.
    Optional RFID allowlist enables restricted access on Authorize.
    Optional authlist enables token-based WebSocket authentication.
    """
    oapp = app
    if (_is_new_app := not (app := gw.unwrap_one(app, FastAPI))):
        app = FastAPI()

    def load_kv_file(pathlike: str, label: str) -> dict[str, list[str]]:
        if not pathlike:
            return {}
        try:
            path = gw.resource(pathlike)
            if not os.path.exists(path):
                gw.error(f"[OCPP] {label} file not found: {path}")
                return {}
            result = {}
            with open(path, "r") as f:
                for lineno, line in enumerate(f, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split(":")
                    key = parts[0].strip()
                    extra = [p.strip() for p in parts[1:]]
                    result[key] = extra
            return result
        except Exception as e:
            gw.abort(f"[OCPP] Failed to read {label} '{pathlike}': {e}")

    _rfid_map = load_kv_file(allowlist, "Allowlist") if allowlist else {}
    _token_map = load_kv_file(authlist, "Authlist") if authlist else {}

    def is_authorized_rfid(rfid: str) -> bool:
        return True if not _rfid_map else rfid in _rfid_map

    def is_authorized_token(token: str | None) -> bool:
        return True if not _token_map else token in _token_map

    @app.websocket("/{path:path}")
    async def websocket_ocpp(websocket: WebSocket, path: str):
        charger_id = path.strip("/").split("/")[-1]
        token = websocket.query_params.get("token")

        if not is_authorized_token(token):
            gw.warn(f"[OCPP] Rejected WebSocket for charger={charger_id}: invalid or missing token")
            await websocket.close(code=4001)
            return

        gw.info(f"[OCPP] WebSocket connected: charger_id={charger_id}, token={token}")
        try:
            await websocket.accept(subprotocol="ocpp1.6")
            _active_cons[charger_id] = websocket

            while True:
                raw = await websocket.receive_text()
                gw.info(f"[OCPP:{charger_id}] → {raw}")

                try:
                    msg = json.loads(raw)
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
                            response_payload = {
                                "transactionId": int(time.time()),
                                "idTagInfo": {"status": "Accepted"}
                            }

                        elif action == "StopTransaction":
                            response_payload = {
                                "idTagInfo": {"status": "Accepted"}
                            }

                        elif action == "StatusNotification":
                            response_payload = {}  # No response fields required

                        else:
                            response_payload = {"status": "Accepted"}

                        response = [3, message_id, response_payload]
                        gw.info(f"[OCPP:{charger_id}] ← {action} => {response_payload}")
                        await websocket.send_text(json.dumps(response))
                    else:
                        gw.warn(f"[OCPP:{charger_id}] Invalid or unsupported message format")

                except Exception as e:
                    gw.error(f"[OCPP:{charger_id}] Message parse error: {e}")
                    gw.debug(traceback.format_exc())

        except WebSocketDisconnect:
            gw.info(f"[OCPP:{charger_id}] WebSocket disconnected")
        except Exception as e:
            gw.error(f"[OCPP:{charger_id}] WebSocket failure: {e}")
            gw.debug(traceback.format_exc())
        finally:
            _active_cons.pop(charger_id, None)

    if allowlist:
        gw.info(f"[OCPP] Loaded allowlist with {len(_rfid_map)} RFID tags")
    if authlist:
        gw.info(f"[OCPP] Loaded authlist with {len(_token_map)} tokens")

    return (app if not oapp else (oapp, app)) if _is_new_app else oapp


setup_csms_app = setup_csms_v16_app 

...

# Views for the main app. These will be used by the main bottle app when we do:
# web app setup - web server start-app

def render_status_view():  # /ocpp/status
    return "OCPP Status - Pending"
