# file: projects/ocpp/evcs.py

import threading
import traceback
from gway import gw, __
import secrets
import base64
from bottle import request
import asyncio, json, random, time, websockets

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


def simulate(
    *,
    host: str = __("[SITE_HOST]", "127.0.0.1") ,
    ws_port: int = __("[WEBSOCKET_PORT]", "9000"),
    rfid: str = "FFFFFFFF",
    cp_path: str = "CPX",
    duration: int = 60,
    kwh_min: float = 0.5,
    kwh_max: float = 1.5,
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
    - kwh_min/kwh_max: approximate energy range per session in kWh.
    """
    host    = gw.resolve(host)
    ws_port = int(gw.resolve(ws_port))
    session_count = parse_repeat(repeat)
    n_threads = int(threads) if threads else 1

    async def orchestrate_all():
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
                    kwh_min,
                    kwh_max,
                    session_count,
                    username,
                    password,
                )
            except Exception as e:
                print(f"[Simulator:coroutine:{idx}] Exception: {e}")

        def run_thread(idx):
            try:
                this_cp_path = _unique_cp_path(cp_path, idx, n_threads)
                asyncio.run(simulate_cp(
                    idx,
                    host,
                    ws_port,
                    rfid,
                    this_cp_path,
                    duration,
                    kwh_min,
                    kwh_max,
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
                t = threading.Thread(target=run_thread, args=(idx,), daemon=True)
                t.start()
                threads_list.append(t)
            try:
                while any(t.is_alive() for t in threads_list):
                    await asyncio.sleep(0.5)
            except asyncio.CancelledError:
                gw.halt("[Simulator] Orchestration cancelled.")
            for t in threads_list:
                t.join()

    if daemon:
        return orchestrate_all()
    else:
        if n_threads == 1:
            asyncio.run(simulate_cp(0, host, ws_port, rfid, cp_path, duration, kwh_min, kwh_max, session_count, username, password))
        else:
            threads_list = []
            for idx in range(n_threads):
                this_cp_path = _unique_cp_path(cp_path, idx, n_threads)
                t = threading.Thread(target=_thread_runner, args=(
                    simulate_cp, idx, host, ws_port, rfid, this_cp_path, duration, kwh_min, kwh_max, session_count, username, password
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
        kwh_min,
        kwh_max,
        session_count,
        username=None,
        password=None,
    ):
    """
    Simulate a single CP session (possibly many times if session_count>1).
    If username/password are provided, use HTTP Basic Auth in the handshake.
    Energy increments are derived from kwh_min/kwh_max.
    """
    cp_name = cp_path
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

            async def listen_to_csms(stop_event, reset_event):
                """Handle incoming CSMS messages until cancelled."""
                try:
                    while True:
                        raw = await ws.recv()
                        print(f"[Simulator:{cp_name} ← CSMS] {raw}")
                        try:
                            msg = json.loads(raw)
                        except json.JSONDecodeError:
                            print(f"[Simulator:{cp_name}] Warning: Received non-JSON message")
                            continue
                        if isinstance(msg, list):
                            if msg[0] == 2:
                                msg_id, action = msg[1], msg[2]
                                await ws.send(json.dumps([3, msg_id, {}]))
                                if action == "RemoteStopTransaction":
                                    print(f"[Simulator:{cp_name}] Received RemoteStopTransaction → stopping transaction")
                                    stop_event.set()
                                elif action == "Reset":
                                    reset_type = ""
                                    if len(msg) > 3 and isinstance(msg[3], dict):
                                        reset_type = msg[3].get("type", "")
                                    print(f"[Simulator:{cp_name}] Received Reset ({reset_type}) → restarting session")
                                    reset_event.set()
                                    stop_event.set()
                            elif msg[0] in (3, 4):
                                # Ignore CallResult and CallError messages
                                continue
                            else:
                                print(f"[Simulator:{cp_name}] Notice: Unexpected message format", msg)
                        else:
                            print(f"[Simulator:{cp_name}] Warning: Expected list message", msg)
                except websockets.ConnectionClosed:
                    print(f"[Simulator:{cp_name}] Connection closed by server")
                    stop_event.set()

            loop_count = 0
            while loop_count < session_count:
                stop_event = asyncio.Event()
                reset_event = asyncio.Event()
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

                # Start listener only after transaction is active so recv calls don't overlap
                listener = asyncio.create_task(listen_to_csms(stop_event, reset_event))

                # MeterValues loop
                actual_duration = random.uniform(duration * 0.75, duration * 1.25)
                interval = actual_duration / 10
                meter = meter_start

                step_min = int((kwh_min * 1000) / 10)
                step_max = int((kwh_max * 1000) / 10)
                for _ in range(10):
                    if stop_event.is_set():
                        print(f"[Simulator:{cp_name}] Stop event triggered—ending meter loop")
                        break
                    meter += random.randint(step_min, step_max)
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

                # Stop listener before sending StopTransaction to avoid recv conflicts
                listener.cancel()
                try:
                    await listener
                except asyncio.CancelledError:
                    pass

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
                next_meter = meter
                last_meter_value = time.monotonic()
                start_idle = time.monotonic()

                while (time.monotonic() - start_idle) < idle_time and not stop_event.is_set():
                    await ws.send(json.dumps([2, "hb", "Heartbeat", {}]))
                    await asyncio.sleep(5)
                    if time.monotonic() - last_meter_value >= 30:
                        idle_step_max = max(2, int(step_max / 100))
                        next_meter += random.randint(0, idle_step_max)
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


                if reset_event.is_set():
                    print(f"[Simulator:{cp_name}] Session reset requested.")
                    continue

                if reset_event.is_set():
                    print(f"[Simulator:{cp_name}] Session reset requested.")
                    continue

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
    _simulator_state["last_command"] = "stop"
    _simulator_state["last_status"] = "Requested stop (will finish current run)..."
    _simulator_state["running"] = False
    # Simulator must check this flag between sessions (not during a blocking one).
    # For a true hard kill, one would need to implement cancellation or kill the thread (not recommended).
    return True

def _simulator_status_json():
    """JSON summary for possible API endpoint / AJAX polling."""
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
    NO card, content in main dashboard layout.
    """

    ws_url = gw.web.build_ws_url("ocpp", "csms")
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
                kwh_min = float(request.forms.get("kwh_min") or 0.5),
                kwh_max = float(request.forms.get("kwh_max") or 1.5),
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

    html = ['<h1>OCPP Charge Point Simulator</h1>']
    if msg:
        html.append(f'<div class="sim-msg">{msg}</div>')

    # Form directly in main (no card)
    html.append('''
    <form method="post" class="simulator-form">
        <div>
            <label>Host:</label>
            <input name="host" value="{host}">
        </div>
        <div>
            <label>Port:</label>
            <input name="ws_port" value="{ws_port}">
        </div>
        <div>
            <label>ChargePoint Path:</label>
            <input name="cp_path" value="{cp_path}">
        </div>
        <div>
            <label>RFID:</label>
            <input name="rfid" value="{rfid}">
        </div>
        <div>
            <label>Duration (s):</label>
            <input name="duration" value="{duration}">
        </div>
        <div>
            <label>Energy Min (kWh):</label>
            <input name="kwh_min" value="{kwh_min}">
        </div>
        <div>
            <label>Energy Max (kWh):</label>
            <input name="kwh_max" value="{kwh_max}">
        </div>
        <div>
            <label>Repeat:</label>
            <select name="repeat">
                <option value="False" {repeat_no}>No</option>
                <option value="True" {repeat_yes}>Yes</option>
            </select>
        </div>
        <div>
            <label>User:</label>
            <input name="username" value="">
        </div>
        <div>
            <label>Pass:</label>
            <input name="password" value="" type="password">
        </div>
        <div class="form-btns">
            <button type="submit" name="action" value="start" {start_dis}>Start</button>
            <button type="submit" name="action" value="stop" {stop_dis}>Stop</button>
        </div>
    </form>
    '''.format(
        host=params.get('host', default_host),
        ws_port=params.get('ws_port', default_ws_port),
        cp_path=params.get('cp_path', default_cp_path),
        rfid=params.get('rfid', default_rfid),
        duration=params.get('duration', 60),
        kwh_min=params.get('kwh_min', 0.5),
        kwh_max=params.get('kwh_max', 1.5),
        repeat_no='selected' if not params.get('repeat') else '',
        repeat_yes='selected' if str(params.get('repeat')).lower() in ('true', '1') else '',
        start_dis='disabled' if running else '',
        stop_dis='disabled' if not running else '',
    ))

    # Status area (no card)
    dot_class = "state-dot online" if running else "state-dot stopped"
    dot_label = "Running" if running else "Stopped"
    html.append(f'''
    <div class="simulator-status">
        <span class="{dot_class}"></span>
        <span>{dot_label}</span>
    </div>
    <div class="simulator-details">
        <label>Last Status:</label> <span class="stat">{state["last_status"] or "-"}</span>
        <label>Last Command:</label> <span class="stat">{state["last_command"] or "-"}</span>
        <label>Started:</label> <span class="stat">{state["start_time"] or "-"}</span>
        <label>Stopped:</label> <span class="stat">{state["stop_time"] or "-"}</span>
    </div>
    ''')

    if error:
        html.append(f'<div class="error"><b>Error:</b><pre>{error}</pre></div>')

    # Panels (params and state)
    html.append('<details class="simulator-panel"><summary>Show Simulator Params</summary>')
    html.append('<pre>')
    html.append(json.dumps(params, indent=2))
    html.append('</pre></details>')

    html.append('<details class="simulator-panel"><summary>Show Simulator State JSON</summary>')
    html.append(f'<pre>{_simulator_status_json()}</pre></details>')

    return "".join(html)
