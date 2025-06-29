# file: projects/ocpp/evcs.py

import threading
import traceback
from gway import gw, __
import secrets
import base64
from bottle import request
import asyncio, json, random, time, websockets
import json
import time

# TODO: Fix this issue found in the logs.
# [Simulator:CPX] Exception: cannot call recv while another coroutine is already running recv or recv_streaming
# It seems to ocurr intermitently. 

def parse_repeat(repeat):
    """Handle repeat=True/'forever'/n logic."""
    if repeat is True or (isinstance(repeat, str) and repeat.lower() in ("true", "forever", "infinite", "loop")):
        return float('inf')
    try:
        n = int(repeat)
        return n if n > 0 else 1
    except Exception:
        return 1

def _thread_runner(target, *args, **kwargs):
    """Helper to run an async function in a thread with its own loop."""
    try:
        asyncio.run(target(*args, **kwargs))
    except Exception as e:
        print(f"[Simulator:thread] Exception: {e}")

def _unique_cp_path(cp_path, idx, total_threads):
    """Append -XXXX to cp_path for each thread when threads > 1."""
    if total_threads == 1:
        return cp_path
    rand_tag = secrets.token_hex(2).upper()  # 4 hex digits, e.g., '1A2B'
    return f"{cp_path}-{rand_tag}"

# TODO: Update sigils to new model

def simulate(
    *,
    host: str = __("[SITE_HOST]", "127.0.0.1") ,
    ws_port: int = __("[WEBSOCKET_PORT]", "9000"),
    rfid: str = "FFFFFFFF",
    cp_path: str = "CPX",
    duration: int = 60,
    repeat=False,
    threads: int = None,
    daemon: bool = True,
    username: str = None,
    password: str = None,
):
    """
    Flexible OCPP 1.6 charger simulator.
    - daemon=False: blocking, always returns after all runs.
    - daemon=True: returns a coroutine for orchestration, user is responsible for awaiting/cancelling.
    - threads: None/1 for one session; >1 to simulate multiple charge points.
    - username/password: If provided, use HTTP Basic Auth on the WS handshake.
    """
    host    = gw.resolve(host)
    ws_port = int(gw.resolve(ws_port))
    session_count = parse_repeat(repeat)
    n_threads = int(threads) if threads else 1

    async def orchestrate_all():
        stop_flags = [threading.Event() for _ in range(n_threads)]
        tasks = []
        threads_list = []

        async def run_task(idx):
            try:
                this_cp_path = _unique_cp_path(cp_path, idx, n_threads)
                await simulate_cp(
                    idx,
                    host,
                    ws_port,
                    rfid,
                    this_cp_path,
                    duration,
                    session_count,
                    username,
                    password,
                )
            except Exception as e:
                print(f"[Simulator:coroutine:{idx}] Exception: {e}")

        def run_thread(idx, stop_flag):
            try:
                this_cp_path = _unique_cp_path(cp_path, idx, n_threads)
                asyncio.run(simulate_cp(
                    idx,
                    host,
                    ws_port,
                    rfid,
                    this_cp_path,
                    duration,
                    session_count,
                    username,
                    password,
                ))
            except Exception as e:
                print(f"[Simulator:thread:{idx}] Exception: {e}")

        if n_threads == 1:
            tasks.append(asyncio.create_task(run_task(0)))
            try:
                await asyncio.gather(*tasks)
            except asyncio.CancelledError:
                print("[Simulator] Orchestration cancelled. Cancelling task(s)...")
                for t in tasks:
                    t.cancel()
                raise
        else:
            for idx in range(n_threads):
                t = threading.Thread(target=run_thread, args=(idx, stop_flags[idx]), daemon=True)
                t.start()
                threads_list.append(t)
            try:
                while any(t.is_alive() for t in threads_list):
                    await asyncio.sleep(0.5)
            except asyncio.CancelledError:
                gw.abort("[Simulator] Orchestration cancelled.")
            for t in threads_list:
                t.join()

    if daemon:
        return orchestrate_all()
    else:
        if n_threads == 1:
            asyncio.run(simulate_cp(0, host, ws_port, rfid, cp_path, duration, session_count, username, password))
        else:
            threads_list = []
            for idx in range(n_threads):
                this_cp_path = _unique_cp_path(cp_path, idx, n_threads)
                t = threading.Thread(target=_thread_runner, args=(
                    simulate_cp, idx, host, ws_port, rfid, this_cp_path, duration, session_count, username, password
                ), daemon=True)
                t.start()
                threads_list.append(t)
            for t in threads_list:
                t.join()

async def simulate_cp(
        cp_idx,
        host,
        ws_port,
        rfid,
        cp_path,
        duration,
        session_count,
        username=None,
        password=None,
    ):
    """
    Simulate a single CP session (possibly many times if session_count>1).
    If username/password are provided, use HTTP Basic Auth in the handshake.
    """
    cp_name = cp_path if session_count == 1 else f"{cp_path}{cp_idx+1}"
    uri     = f"ws://{host}:{ws_port}/{cp_name}"
    headers = {}
    if username and password:
        userpass = f"{username}:{password}"
        b64 = base64.b64encode(userpass.encode("utf-8")).decode("ascii")
        headers["Authorization"] = f"Basic {b64}"

    try:
        async with websockets.connect(
            uri,
            subprotocols=["ocpp1.6"],
            additional_headers=headers,
        ) as ws:
            print(f"[Simulator:{cp_name}] Connected to {uri} (auth={'yes' if headers else 'no'})")

            async def listen_to_csms(stop_event):
                try:
                    while True:
                        raw = await ws.recv()
                        print(f"[Simulator:{cp_name} ← CSMS] {raw}")
                        try:
                            msg = json.loads(raw)
                        except json.JSONDecodeError:
                            print(f"[Simulator:{cp_name}] Warning: Received non-JSON message")
                            continue
                        if isinstance(msg, list) and msg[0] == 2:
                            msg_id, action, payload = msg[1], msg[2], (msg[3] if len(msg) > 3 else {})
                            await ws.send(json.dumps([3, msg_id, {}]))
                            if action == "RemoteStopTransaction":
                                print(f"[Simulator:{cp_name}] Received RemoteStopTransaction → stopping transaction")
                                stop_event.set()
                        else:
                            print(f"[Simulator:{cp_name}] Notice: Unexpected message format", msg)
                except websockets.ConnectionClosed:
                    print(f"[Simulator:{cp_name}] Connection closed by server")
                    stop_event.set()

            loop_count = 0
            while loop_count < session_count:
                stop_event = asyncio.Event()

                # Start listener for this session
                listener = asyncio.create_task(listen_to_csms(stop_event))

                # Initial handshake
                await ws.send(json.dumps([2, "boot", "BootNotification", {
                    "chargePointModel": "Simulator",
                    "chargePointVendor": "SimVendor"
                }]))
                await ws.recv()
                await ws.send(json.dumps([2, "auth", "Authorize", {"idTag": rfid}]))
                await ws.recv()

                # StartTransaction
                meter_start = random.randint(1000, 2000)
                await ws.send(json.dumps([2, "start", "StartTransaction", {
                    "connectorId": 1,
                    "idTag": rfid,
                    "meterStart": meter_start
                }]))
                resp = await ws.recv()
                tx_id = json.loads(resp)[2].get("transactionId")
                print(f"[Simulator:{cp_name}] Transaction {tx_id} started at meter {meter_start}")

                # MeterValues loop
                actual_duration = random.uniform(duration * 0.75, duration * 1.25)
                interval = actual_duration / 10
                meter = meter_start

                for _ in range(10):
                    if stop_event.is_set():
                        print(f"[Simulator:{cp_name}] Stop event triggered—ending meter loop")
                        break
                    meter += random.randint(50, 150)
                    meter_kwh = meter / 1000.0
                    await ws.send(json.dumps([2, "meter", "MeterValues", {
                        "connectorId": 1,
                        "transactionId": tx_id,
                        "meterValue": [{
                            "timestamp": time.strftime('%Y-%m-%dT%H:%M:%S') + "Z",
                            "sampledValue": [{
                                "value": f"{meter_kwh:.3f}",
                                "measurand": "Energy.Active.Import.Register",
                                "unit": "kWh",
                                "context": "Sample.Periodic"
                            }]
                        }]
                    }]))
                    await asyncio.sleep(interval)

                # StopTransaction
                await ws.send(json.dumps([2, "stop", "StopTransaction", {
                    "transactionId": tx_id,
                    "idTag": rfid,
                    "meterStop": meter
                }]))
                await ws.recv()
                print(f"[Simulator:{cp_name}] Transaction {tx_id} stopped at meter {meter}")

                # Idle phase: send heartbeat and idle meter value
                idle_time = 20 if session_count == 1 else 60
                idle_counter = 0
                next_meter = meter
                last_meter_value = time.monotonic()
                start_idle = time.monotonic()

                while (time.monotonic() - start_idle) < idle_time and not stop_event.is_set():
                    await ws.send(json.dumps([2, "hb", "Heartbeat", {}]))
                    await asyncio.sleep(5)
                    idle_counter += 5
                    if time.monotonic() - last_meter_value >= 30:
                        next_meter += random.randint(0, 2)
                        next_meter_kwh = next_meter / 1000.0
                        await ws.send(json.dumps([2, "meter", "MeterValues", {
                            "connectorId": 1,
                            "meterValue": [{
                                "timestamp": time.strftime('%Y-%m-%dT%H:%M:%S') + "Z",
                                "sampledValue": [{
                                    "value": f"{next_meter_kwh:.3f}",
                                    "measurand": "Energy.Active.Import.Register",
                                    "unit": "kWh",
                                    "context": "Sample.Clock"
                                }]
                            }]
                        }]))
                        last_meter_value = time.monotonic()
                        print(f"[Simulator:{cp_name}] Idle MeterValues sent.")

                listener.cancel()
                try:
                    await listener
                except asyncio.CancelledError:
                    pass

                loop_count += 1
                if session_count == float('inf'):
                    continue  # loop forever

            print(f"[Simulator:{cp_name}] Simulation ended.")
    except Exception as e:
        print(f"[Simulator:{cp_name}] Exception: {e}")


# --- Simulator control state ---
_simulator_state = {
    "running": False,
    "last_status": "",
    "last_command": None,
    "last_error": "",
    "thread": None,
    "start_time": None,
    "stop_time": None,
    "params": {},
}


def _run_simulator_thread(params):
    """Background runner for the simulator, updating state as it runs."""
    global _simulator_state
    try:
        _simulator_state["last_status"] = "Starting..."
        coro = simulate(**params)
        if hasattr(coro, "__await__"):  # coroutine (daemon=True)
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(coro)
        _simulator_state["last_status"] = "Simulator finished."
    except Exception as e:
        _simulator_state["last_status"] = "Error"
        _simulator_state["last_error"] = f"{e}\n{traceback.format_exc()}"
    finally:
        _simulator_state["running"] = False
        _simulator_state["stop_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
        _simulator_state["thread"] = None


def _start_simulator(params=None):
    """Start the simulator in a background thread."""
    global _simulator_state
    if _simulator_state["running"]:
        return False  # Already running
    _simulator_state["last_error"] = ""
    _simulator_state["last_command"] = "start"
    _simulator_state["last_status"] = "Simulator launching..."
    _simulator_state["params"] = params or {}
    _simulator_state["running"] = True
    _simulator_state["start_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
    _simulator_state["stop_time"] = None
    t = threading.Thread(target=_run_simulator_thread, args=(_simulator_state["params"],), daemon=True)
    _simulator_state["thread"] = t
    t.start()
    return True

def _stop_simulator():
    """Stop the simulator. (Note: true coroutine interruption is not implemented.)"""
    global _simulator_state
    _simulator_state["last_command"] = "stop"
    _simulator_state["last_status"] = "Requested stop (will finish current run)..."
    _simulator_state["running"] = False
    # Simulator must check this flag between sessions (not during a blocking one).
    # For a true hard kill, one would need to implement cancellation or kill the thread (not recommended).
    return True

def _simulator_status_json():
    """JSON summary for possible API endpoint / AJAX polling."""
    global _simulator_state
    return json.dumps({
        "running": _simulator_state["running"],
        "last_status": _simulator_state["last_status"],
        "last_command": _simulator_state["last_command"],
        "last_error": _simulator_state["last_error"],
        "params": _simulator_state["params"],
        "start_time": _simulator_state["start_time"],
        "stop_time": _simulator_state["stop_time"],
    }, indent=2)


def view_cp_simulator(*args, **kwargs):
    """
    Web UI for the OCPP simulator (single session only).
    Start/stop, view state, error messages, and current config.
    """
    global _simulator_state

    # Get default host/port from CSMS websocket
    ws_url = gw.web.build_ws_url(project="ocpp.csms")
    default_host = ws_url.split("://")[-1].split(":")[0]
    default_ws_port = ws_url.split(":")[-1].split("/")[0] if ":" in ws_url else "9000"
    default_cp_path = "CPX"
    default_rfid = "FFFFFFFF"

    msg = ""
    if request.method == "POST":
        action = request.forms.get("action")
        if action == "start":
            sim_params = dict(
                host = request.forms.get("host") or default_host,
                ws_port = int(request.forms.get("ws_port") or default_ws_port),
                cp_path = request.forms.get("cp_path") or default_cp_path,
                rfid = request.forms.get("rfid") or default_rfid,
                duration = int(request.forms.get("duration") or 60),
                repeat = request.forms.get("repeat") or False,
                daemon = True,
                username = request.forms.get("username") or None,
                password = request.forms.get("password") or None,
            )
            started = _start_simulator(sim_params)
            msg = "Simulator started." if started else "Simulator is already running."
        elif action == "stop":
            _stop_simulator()
            msg = "Stop requested. Simulator will finish current session before stopping."
        else:
            msg = "Unknown action."

    state = dict(_simulator_state)
    running = state["running"]
    error = state["last_error"]
    params = state["params"]

    html = ['<h1>OCPP Charger Simulator</h1>']
    if msg:
        html.append(f'<div style="margin-bottom:1em;color:#0a0">{msg}</div>')

    html.append(f'''
    <form method="post" style="margin-bottom:1.2em;display:flex;gap:20px;align-items:flex-end;">
        <div>
            <label>Host:<br><input name="host" value="{params.get('host', default_host)}" style="width:130px"></label>
        </div>
        <div>
            <label>Port:<br><input name="ws_port" value="{params.get('ws_port', default_ws_port)}" style="width:70px"></label>
        </div>
        <div>
            <label>ChargePoint Path:<br><input name="cp_path" value="{params.get('cp_path', default_cp_path)}" style="width:90px"></label>
        </div>
        <div>
            <label>RFID:<br><input name="rfid" value="{params.get('rfid', default_rfid)}" style="width:110px"></label>
        </div>
        <div>
            <label>Duration (s):<br><input name="duration" value="{params.get('duration', 60)}" style="width:60px"></label>
        </div>
        <div>
            <label>Repeat:<br>
                <select name="repeat" style="width:80px">
                    <option value="False" {'selected' if not params.get('repeat') else ''}>No</option>
                    <option value="True" {'selected' if str(params.get('repeat')).lower() in ('true', '1') else ''}>Yes</option>
                </select>
            </label>
        </div>
        <div>
            <label>User:<br><input name="username" value="" style="width:80px"></label>
        </div>
        <div>
            <label>Pass:<br><input name="password" value="" type="password" style="width:80px"></label>
        </div>
        <div>
            <button type="submit" name="action" value="start" {'disabled' if running else ''}>Start</button>
            <button type="submit" name="action" value="stop" {'disabled' if not running else ''}>Stop</button>
        </div>
    </form>
    ''')

    html.append('<div style="margin-bottom:0.8em;">')
    html.append(f'<b>Status:</b> {"🟢 Running" if running else "⚪ Stopped"}<br>')
    html.append(f'<b>Last Status:</b> {state["last_status"]}<br>')
    html.append(f'<b>Last Command:</b> {state["last_command"] or "-"}<br>')
    html.append(f'<b>Started:</b> {state["start_time"] or "-"}<br>')
    html.append(f'<b>Stopped:</b> {state["stop_time"] or "-"}<br>')
    html.append('</div>')

    if error:
        html.append(f'<div style="background:#faa;color:#a00;padding:0.8em 1em;border-radius:7px;margin-bottom:1em;"><b>Error:</b><pre>{error}</pre></div>')

    html.append('<details style="margin-bottom:1.2em;"><summary style="font-weight:bold;cursor:pointer;">Show Simulator Params</summary>')
    html.append('<pre style="margin:0.4em 0 0 0;font-size:1.02em;background:#222;color:#fff;border-radius:6px;padding:10px 12px;">')
    html.append(json.dumps(params, indent=2))
    html.append('</pre></details>')

    html.append('<details><summary style="font-weight:bold;cursor:pointer;">Show Simulator State JSON</summary>')
    html.append(f'<pre style="margin:0.4em 0 0 0;font-size:1.02em;background:#222;color:#fff;border-radius:6px;padding:10px 12px;">{_simulator_status_json()}</pre>')
    html.append('</details>')

    return "".join(html)
