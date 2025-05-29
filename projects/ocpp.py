
import json
import traceback
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from typing import Dict
from gway import gw

# These are ports of the functions originally tested on the eTron charger
# and are used to simulate the CSMS server. Ported from gsol to gway.

def setup_sink_app(*, 
            host='[OCPP_CSMS_HOST|0.0.0.0]', 
            port='[OCPP_CSMS_PORT|9000]', 
            app=None,
        ):
    """Basic OCPP passive sink for messages, acting as a dummy CSMS server."""
    import json
    import traceback
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect

    if app is None: app = FastAPI()

    @app.websocket("/{path:path}")
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
                        # It's a Call message
                        message_id = msg[1]
                        action = msg[2]
                        payload = msg[3] if len(msg) > 3 else {}

                        gw.info(f"[OCPP:{path}] -> Action: {action} | Payload: {payload}")

                        # Respond with a CallResult (OCPP type 3)
                        response = [3, message_id, {"status": "Accepted"}]
                        await websocket.send_text(json.dumps(response))
                        gw.info(f"[OCPP:{path}] <- Acknowledged: {response}")
                    else:
                        # Unknown or non-call message
                        gw.warning(f"[OCPP:{path}] Received non-Call message or malformed")

                except Exception as e:
                    gw.error(f"[OCPP:{path}] Error parsing message:", str(e))
                    gw.debug(traceback.format_exc())

        except WebSocketDisconnect:
            gw.info(f"[OCPP:{path}] Disconnected")
        except Exception as e:
            gw.error(f"[OCPP:{path}] WebSocket error:", str(e))
            gw.debug(traceback.format_exc())

    gw.info(f"Setup passive OCPP sink on {host}:{port}")
    return app
    

# Track active connections
_active_cons: Dict[str, WebSocket] = {}


def setup_csms_app(*,
        host='[OCPP_CSMS_HOST|0.0.0.0]', 
        port='[OCPP_CSMS_PORT|9000]', 
        app=None,
        allowlist=None,
    ):
    """
    OCPP 1.6 CSMS implementation with:
    - RFID Authorize validation via optional allowlist file
    - WebSocket session tracking
    - Basic status page at /
    - UI support for de-authorizing chargers
    """

    if app is None:
        app = FastAPI()

    static_dir = gw.resource("data", "static")
    templates_dir = gw.resource("data", "ocpp", "templates")
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    templates = Jinja2Templates(directory=templates_dir)

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
                    if not line: continue
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

    @app.get("/", response_class=HTMLResponse)
    async def status_page(request: Request):
        return templates.TemplateResponse("status.html", {
            "request": request,
            "connections": _active_cons.keys()
        })

    @app.post("/disconnect/{charger_id}")
    async def disconnect_charger(charger_id: str):
        ws = _active_cons.get(charger_id)
        if ws:
            await ws.close(code=1000)
            return {"status": "disconnected"}
        return {"status": "not_found"}

    if allowlist:
        _ = load_allowlist()  # Validates on startup
        gw.debug("Allowlist loaded without errors.")

    gw.info(f"Setup OCPP 1.6 auth sink on {host}:{port} (allowlist={allowlist})")
    return app
