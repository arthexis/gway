from gway import gw

# These are ports the functions that were originally tested on the eTron charger
# and are used to simulate the CSMS server. Ported from gsol to gway.

def setup_sink_app(*, 
                   host='[OCPP_CSMS_HOST|0.0.0.0]', 
                   port='[OCPP_CSMS_PORT|9000]', 
                   app=None,
                    ):
    """Basic OCPP passive sink for messages, acting as a dummy CSMS server. DO NOT MODIFY.
        This function was tested on a real eTron charger on 2025/4/5, prior to ocpp__start_dummy.
    """
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    import json
    import traceback

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
                        gw.error(f"[OCPP:{path}] Received non-Call message or malformed")

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
    

