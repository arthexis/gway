from datetime import date, datetime
from gway import gw, requires


@requires("uvicorn", "fastapi", "dateparser")
def ocpp__start_csms_v3(*,
        host="[OCPP_CSMS_HOST]", port="[OCPP_CSMS_PORT]", endpoint="csms", reset=False,
        txn_id=42, interval=300, auth=False, logfile=None, filter=None, ignore=None, evccids=None,
        cutoff=None, report=None, qr_auth_url=None, work_hours=None, timeout=30, paths=None, 
    ):
    """Act as a CSMS server that we can point a charging station or simulator to.
    """
    import uvicorn, json, os
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.middleware.cors import CORSMiddleware
    from dateparser import parse as parse_date

    app = FastAPI()
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    if paths:
        allowed_paths = paths if isinstance(paths, list) else [p.strip() for p in paths.split(",")]
    else:
        allowed_paths = None
    gw.info(f"Starting OCPP CSMS server on ws://{host}:{port}/{endpoint}/{{path}} reset={reset}")
    if qr_auth_url:
        # Workflow for QR Auth:
        # 1. User plugs in car to charger or scanner QR code to receive instructions.
        # 2. Charger sends BootNotification + Authorize to local CSMS.
        # 3. Local CSMS sends auth request to central server to which the QR code is linked.
        # 4. User approves the request on central server and local CSMS authorizes the charger.
        # Notes: RFID has been removed as a feature.
        gw.info(f"Using QR auth URL: {qr_auth_url}")

    reset_done = set()
    next_txn_id = txn_id
    cutoff_dt = parse_date(cutoff) if cutoff else None
    session_data = {}
    # We store each received QR authorization in a cache until its expiration time. 
    # However we only use this cache if we cannot reach the QR auth URL. If we can, we should request a new authorization.
    # We want to store the full response from the server so we can use it later.
    qr_data = {}  

    def should_log(action):
        return not (filter and action not in filter) and not (ignore and action in ignore)

    def log_event(path, label, data=None):
        gw.info(f"[OCPP:CSMS:{path}] {label}", data)
        if logfile:
            with open(gw.resource(logfile), "a") as f:
                f.write(json.dumps({
                    "timestamp": gw.timestamp(), "path": path, "event": label, "data": data
                }, default=str) + "\n")

    def save_report(path):
        data = session_data.get(path)
        if not data:
            return
        charger_id = data.get("boot", {}).get("chargePointSerialNumber", "unknown")
        timestamp = data.get("start_time", gw.timestamp())
        filename = f"{charger_id}_{timestamp.replace(':', '_')}.json"

        if report:
            gw.info(f"Saving report for {path} to {report}/{filename}")
            path_report = gw.resource(report)
            if os.path.isdir(path_report):
                with open(path_report / filename, "w") as f:
                    f.write(json.dumps(data, default=str))
            else:
                with open(path_report, "a") as f:
                    f.write(json.dumps(data, default=str) + "\n")

    def handle_auth(path):
        import requests

        # Convert HH:MM string to datetime.time
        def parse_time_str(t):
            return datetime.strptime(t, "%H:%M").time()

        # Check work hours
        if work_hours:
            now_time = datetime.now().time()
            within_hours = any(
                parse_time_str(start) <= now_time <= parse_time_str(end)
                for (start, end) in work_hours
            )
            if not within_hours:
                gw.warning(f"Rejected auth for {path}: outside of work hours")
                return {"status": "Rejected"}

        if qr_auth_url:
            try:
                res = requests.post(qr_auth_url, json={"path": path})
                if res.status_code == 200:
                    qr_data[path] = res.json()  # See below on what we expect to get here (at least)
                    return qr_data[path]
                else:
                    gw.error(f"QR auth failed: {res.status_code} {res.text}")
            except Exception as e:
                gw.error(f"QR auth request failed: {e}")
                if path in qr_data:
                    cached = qr_data[path]
                    exp = cached.get("expiration")
                    if exp:
                        try:
                            from dateutil.parser import parse as parse_date
                            if parse_date(exp) < datetime.now(utc=True):
                                gw.warning(f"Cached QR auth expired for {path}")
                                return {"status": "Rejected"}
                        except Exception as ex:
                            gw.error(f"Invalid expiration format for cached QR auth: {exp} ({ex})")
                    gw.warning(f"Using cached QR auth for {path}")
                    return cached
                else:
                    return {"status": "Rejected"}
        else:
            return {"status": "Accepted" if auth else "Rejected"}

    def handle_evccid_auth(evccid):
        with open(evccids, "r") as f:
            allowed_evccids = set(line.strip() for line in f.readlines())
        if evccid in allowed_evccids:   
            return {"status": "Accepted"}
        return {"status": "Rejected"}

    # This is the endpoint that the charging station or simulator will connect to.
    @app.websocket(f"/{endpoint}/{{path}}")
    async def websocket_ocpp(websocket: WebSocket, path: str):
        nonlocal next_txn_id
        if allowed_paths and path not in allowed_paths:
            await websocket.close()
            gw.warning(f"Rejected path {path}: not in allowed paths")
            return
        await websocket.accept()
        log_event(path, "Connection accepted")
        sent_reset = False
        session_data[path] = {
            "boot": None, "status": [], "start_time": None,
            "stop_time": None, "meter_values": [], "idTag": None
        }

        try:
            while True:
                raw = await websocket.receive_text()
                local_timestamp = datetime.now(utc=True)
                try:
                    msg = json.loads(raw)
                    if not isinstance(msg, list) or len(msg) < 3 or msg[0] != 2:
                        continue

                    _, message_id, action, *rest = msg
                    payload = rest[0] if rest else {}

                    # Check for cutoff timestamp
                    if cutoff_dt and payload.get("timestamp"):
                        try:
                            if parse_date(payload["timestamp"]) < cutoff_dt:
                                continue
                        except:
                            pass

                    log_event(path, f"CALL {action}", payload)
                    if not should_log(action):
                        continue

                    response = [3, message_id, {}]

                    if reset and path not in reset_done:
                        reset_done.add(path)
                        for cmd in ["Reset", "ClearCache"]:
                            msg_id = f"{cmd.lower()}-{gw.timestamp()}"
                            body = {"type": "Hard"} if cmd == "Reset" else {}
                            await websocket.send_text(json.dumps([2, msg_id, cmd, body]))
                            log_event(path, f"Sent {cmd}")

                    if action == "BootNotification":
                        session_data[path]["boot"] = payload
                        response[2] = {"status": "Accepted", "currentTime": gw.timestamp(), "interval": interval}
                        log_event(path, "BootNotification processed")

                    elif action == "Authorize":
                        tag = payload.get("idTag")
                        evccid = payload.get("customData", {}).get("evccid")  # or another field
                        session_data[path]["idTag"] = tag
                        session_data[path]["evccid"] = evccid

                        # Prioritize EVCCID auth if available
                        if evccid and evccids:
                            result = handle_evccid_auth(evccid)
                            gw.info(f"Authorize EVCCID '{evccid}' -> {result['status']}")
                        else:
                            result = handle_auth(path)
                            gw.info(f"Authorize '{tag}' -> {result['status']}")

                        session_data[path]["authorized"] = result["status"] == "Accepted"
                        response[2] = {"idTagInfo": result}
                        
                    elif action == "StartTransaction":
                        tag = payload.get("idTag")

                        if qr_auth_url and not session_data[path].get("authorized", False):
                            # Delay response until user has approved via QR
                            import asyncio
                            gw.info(f"Waiting for QR auth for {path}...")
                            for _ in range(int(timeout)):  # wait up to 30 seconds
                                await asyncio.sleep(1)
                                if session_data[path].get("authorized", False):
                                    gw.info(f"QR auth approved for {path}")
                                    break
                            else:
                                gw.warning(f"QR auth not approved in time for {path}")

                        authorized = session_data[path].get("authorized", False)
                        status = "Accepted" if authorized else "Invalid"
                        response[2] = {
                            "transactionId": next_txn_id,
                            "idTagInfo": {"status": status},
                        }

                        session_data[path]["start_time"] = gw.timestamp()
                        log_event(path, f"StartTransaction from '{tag}' -> {status}")

                        if authorized:
                            next_txn_id += 1

                    elif action == "StopTransaction":
                        session_data[path]["stop_time"] = gw.timestamp()
                        log_event(path, "StopTransaction received")
                        save_report(path)

                    elif action == "StatusNotification":
                        session_data[path]["status"].append(payload)
                        log_event(path, f"StatusNotification -> {payload.get('status')}")

                    elif action == "MeterValues":
                        session_data[path]["meter_values"].append(payload)
                        log_event(path, "MeterValues received")

                    elif action == "Heartbeat":
                        response[2] = {"currentTime": gw.timestamp()}
                        log_event(path, "Heartbeat")

                    else:
                        log_event(path, f"Unhandled action: {action}")

                    await websocket.send_text(json.dumps(response))
                    log_event(path, f"Sent ACK: {response}")

                except json.JSONDecodeError:
                    log_event(path, "Invalid JSON received")

        except WebSocketDisconnect:
            log_event(path, "Disconnected")

    # External endpoint to handle QR authorization "manually".
    # This is used when the charger is not connected to the internet and we need to approve the QR code locally.
    if qr_data is not None:
        @app.post(f"/{endpoint}/qr/approve/{{path}}")
        async def approve_qr(path: str):
            qr_data[path] = {"status": "Accepted"}
            session_data.setdefault(path, {})["authorized"] = True
            return {"status": "approved"}

        # TODO: When paths is given generate an index-like page where a local user can see the list of paths and approve them.
        # Generate a QR code (gsol.qr.create) for each path and show the status of each path.

    from fastapi.responses import HTMLResponse

    if allowed_paths:
        @app.get(f"/{endpoint}")
        async def list_paths():
            html = "<h1>Approve Chargers</h1><ul>"
            for p in allowed_paths:
                qr_img = gw.qr_code.generate_img(f"http://{host}:{port}/{endpoint}/qr/approve/{p}", as_base64=True)
                status = "Authorized" if session_data.get(p, {}).get("authorized") else "Pending"
                html += f"<li><p>{p}: {status}</p><img src='data:image/png;base64,{qr_img}' /></li>"
            html += "</ul>"
            return HTMLResponse(html)

        
    uvicorn.run(app, host=host, port=int(port))
