# file: projects/ocpp/sink.py

import json
import traceback
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from gway import gw


def setup_sink_app(*, app=None):
    """
    Basic OCPP passive sink for messages, acting as a dummy CSMS server.
    This won't pass compliance or provide authentication. It just accepts and logs all.
    Note: This version of the app was tested at the EVCS with real EVs.
    """
    # A - This line ensures we find just the kind of app we need or create one if missing
    oapp = app
    match app:
        case FastAPI() as f:
            app = f
            _is_new_app = False
        case list() | tuple() as seq:
            app = next((x for x in seq if isinstance(x, FastAPI)), None)
            _is_new_app = app is None
        case None:
            _is_new_app = True
        case _ if isinstance(app, FastAPI):
            _is_new_app = False
        case _ if hasattr(app, "__iter__") and not isinstance(app, (str, bytes, bytearray)):
            app = next((x for x in app if isinstance(x, FastAPI)), None)
            _is_new_app = app is None
        case _:
            _is_new_app = app is None or not isinstance(app, FastAPI)
    if _is_new_app:
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
