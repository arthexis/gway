# file: projects/ocpp/evcs.py

import threading
import traceback
from gway import gw, __
import secrets
import base64
from bottle import request
import asyncio, json, random, time, websockets
import os

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
    duration: int = 600,
    kwh_min: float = 30,
    kwh_max: float = 60,
    pre_charge_delay: float = 0,
    repeat=False,
    threads: int = None,
    daemon: bool = True,
    interval: float = 5,
    username: str = None,
    password: str = None,
    cp: int = 1,
):
    """
    Flexible OCPP 1.6 charger simulator.
    - daemon=False: blocking, always returns after all runs.
    - daemon=True: returns a coroutine for orchestration, user is responsible for awaiting/cancelling.
    - threads: None/1 for one session; >1 to simulate multiple charge points.
    - username/password: If provided, use HTTP Basic Auth on the WS handshake.
    - kwh_min/kwh_max: approximate energy range per session in kWh.
    - pre_charge_delay: wait this many seconds before starting a session while
      still sending Heartbeats.
    - cp: which simulator slot to update when persisting state.
    """
    host    = gw.resolve(host)
    ws_port = int(gw.resolve(ws_port))
    session_count = parse_repeat(repeat)
    n_threads = int(threads) if threads else 1

    # record starting state for CLI usage
    sim_params = dict(
        host=host,
        ws_port=ws_port,
        rfid=rfid,
        cp_path=cp_path,
        duration=duration,
        interval=interval,
        kwh_min=kwh_min,
        kwh_max=kwh_max,
        pre_charge_delay=pre_charge_delay,
        repeat=repeat,
        threads=threads,
        username=username,
        password=password,
        daemon=daemon,
    )
    state = _simulators.get(cp, _simulators[1])
    state.update(
        {
            "last_command": "start",
            "last_status": "Simulator launching...",
            "running": True,
            "params": sim_params,
            "start_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "stop_time": None,
        }
    )
    _save_state_file(_simulators)

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
                    pre_charge_delay,
                    session_count,
                    interval,
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
                    pre_charge_delay,
                    session_count,
                    interval,
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
        state["last_status"] = "Simulator finished."
        state["running"] = False
        state["stop_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
        _save_state_file(_simulators)

    if daemon:
        return orchestrate_all()
    else:
        if n_threads == 1:
            asyncio.run(simulate_cp(0, host, ws_port, rfid, cp_path, duration, kwh_min, kwh_max, pre_charge_delay, session_count, interval, username, password))
        else:
            threads_list = []
            for idx in range(n_threads):
                this_cp_path = _unique_cp_path(cp_path, idx, n_threads)
                t = threading.Thread(target=_thread_runner, args=(
                    simulate_cp, idx, host, ws_port, rfid, this_cp_path, duration, kwh_min, kwh_max, pre_charge_delay, session_count, interval, username, password
                ), daemon=True)
                t.start()
                threads_list.append(t)
            for t in threads_list:
                t.join()
        state["last_status"] = "Simulator finished."
        state["running"] = False
        state["stop_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
        _save_state_file(_simulators)

async def simulate_cp(
        cp_idx,
        host,
        ws_port,
        rfid,
        cp_path,
        duration,
        kwh_min,
        kwh_max,
        pre_charge_delay,
        session_count,
        interval=5,
        username=None,
        password=None,
    ):
    """
    Simulate a single CP session (possibly many times if ``session_count`` > 1).
    ``interval`` controls how often MeterValues are sent.
    ``pre_charge_delay`` specifies how long to wait before starting a
    transaction while still sending Heartbeats and idle MeterValues.
    If username/password are provided, use HTTP Basic Auth in the handshake.
    Energy increments are derived from ``kwh_min``/``kwh_max``.
    """
    cp_name = cp_path
    state = _simulators.get(cp_idx + 1, _simulators[1])
    uri     = f"ws://{host}:{ws_port}/{cp_name}"
    headers = {}
    if username and password:
        userpass = f"{username}:{password}"
        b64 = base64.b64encode(userpass.encode("utf-8")).decode("ascii")
        headers["Authorization"] = f"Basic {b64}"

    loop_count = 0
    while loop_count < session_count:
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
                        _simulators[cp_idx + 1]["last_status"] = "Connection closed"
                        stop_event.set()

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

                meter_start = random.randint(1000, 2000)
                actual_duration = random.uniform(duration * 0.75, duration * 1.25)
                steps = max(1, int(actual_duration / interval))
                step_min = max(1, int((kwh_min * 1000) / steps))
                step_max = max(1, int((kwh_max * 1000) / steps))

                if pre_charge_delay > 0:
                    state["last_status"] = "Waiting"
                    next_meter = meter_start
                    last_mv = time.monotonic()
                    start_delay = time.monotonic()
                    while (time.monotonic() - start_delay) < pre_charge_delay:
                        await ws.send(json.dumps([2, "hb", "Heartbeat", {}]))
                        await ws.recv()
                        await asyncio.sleep(5)
                        if time.monotonic() - last_mv >= 30:
                            idle_step_max = max(2, int(step_max / 100))
                            next_meter += random.randint(0, idle_step_max)
                            next_kwh = next_meter / 1000.0
                            await ws.send(json.dumps([2, "meter", "MeterValues", {
                                "connectorId": 1,
                                "meterValue": [{
                                    "timestamp": time.strftime('%Y-%m-%dT%H:%M:%S') + "Z",
                                    "sampledValue": [{
                                        "value": f"{next_kwh:.3f}",
                                        "measurand": "Energy.Active.Import.Register",
                                        "unit": "kWh",
                                        "context": "Sample.Clock"
                                    }]
                                }]
                            }]))
                            await ws.recv()
                            last_mv = time.monotonic()

                # StartTransaction
                await ws.send(json.dumps([2, "start", "StartTransaction", {
                    "connectorId": 1,
                    "idTag": rfid,
                    "meterStart": meter_start
                }]))
                resp = await ws.recv()
                tx_id = json.loads(resp)[2].get("transactionId")
                print(f"[Simulator:{cp_name}] Transaction {tx_id} started at meter {meter_start}")
                state["last_status"] = "Running"

                # Start listener only after transaction is active so recv calls don't overlap
                listener = asyncio.create_task(listen_to_csms(stop_event, reset_event))

                # MeterValues loop
                meter = meter_start
                for _ in range(steps):
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
                # give the event loop a moment to finalize the cancelled recv
                await asyncio.sleep(0)

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

                loop_count += 1
                if session_count == float('inf'):
                    continue  # loop forever

        except websockets.ConnectionClosedError as e:
            print(f"[Simulator:{cp_name}] Warning: {e} -- reconnecting")
            state["last_status"] = "Reconnecting"
            await asyncio.sleep(1)
            continue
        except Exception as e:
            print(f"[Simulator:{cp_name}] Exception: {e}")
            break

    print(f"[Simulator:{cp_name}] Simulation ended.")
    state["last_status"] = "Stopped"
    state["running"] = False
    state["stop_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
    _save_state_file(_simulators)


# --- Simulator control state ---
_DEFAULT_STATE = {
    "running": False,
    "last_status": "",
    "last_command": None,
    "last_error": "",
    "thread": None,
    "start_time": None,
    "stop_time": None,
    "pid": None,
    "params": {},
}

# states for CP1 and CP2
_simulators = {
    1: dict(_DEFAULT_STATE),
    2: dict(_DEFAULT_STATE),
}

# Persist simulator state across processes
STATE_FILE = gw.resource("work", "ocpp", "simulator.json")

def _load_state_file():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def _save_state_file(states: dict):
    try:
        safe = {}
        for cp, st in states.items():
            clean = {k: st.get(k) for k in _DEFAULT_STATE if k != "thread"}
            safe[str(cp)] = clean
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(safe, f)
    except Exception:
        pass

def _pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    else:
        return True

# Initialize from saved state if available
try:
    saved = _load_state_file()
    for cp in (1, 2):
        cp_key = str(cp)
        if cp_key in saved and isinstance(saved[cp_key], dict):
            for k in _DEFAULT_STATE:
                if k == "thread":
                    continue
                if k in saved[cp_key]:
                    _simulators[cp][k] = saved[cp_key][k]
            if not _pid_alive(_simulators[cp].get("pid")):
                _simulators[cp]["running"] = False
except Exception:
    pass


def _run_simulator_thread(cp_idx, params):
    """Background runner for the simulator, updating state as it runs."""
    state = _simulators[cp_idx]
    try:
        state["last_status"] = "Starting..."
        state["pid"] = os.getpid()
        _save_state_file(_simulators)
        coro = simulate(**params, cp=cp_idx)
        if hasattr(coro, "__await__"):  # coroutine (daemon=True)
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(coro)
        state["last_status"] = "Simulator finished."
    except Exception as e:
        state["last_status"] = "Error"
        state["last_error"] = f"{e}\n{traceback.format_exc()}"
    finally:
        state["running"] = False
        state["stop_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
        state["thread"] = None
        _save_state_file(_simulators)


def _start_simulator(params=None, cp=1):
    """Start the simulator in a background thread."""
    state = _simulators[cp]
    if state["running"]:
        return False  # Already running
    state["last_error"] = ""
    state["last_command"] = "start"
    state["last_status"] = "Simulator launching..."
    state["params"] = params or {}
    state["running"] = True
    state["start_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
    state["stop_time"] = None
    state["pid"] = os.getpid()
    _save_state_file(_simulators)
    t = threading.Thread(target=_run_simulator_thread, args=(cp, state["params"]), daemon=True)
    state["thread"] = t
    t.start()
    return True

def _stop_simulator(cp=1):
    """Stop the simulator. (Note: true coroutine interruption is not implemented.)"""
    state = _simulators[cp]
    state["last_command"] = "stop"
    state["last_status"] = "Requested stop (will finish current run)..."
    state["running"] = False
    # Simulator must check this flag between sessions (not during a blocking one).
    # For a true hard kill, one would need to implement cancellation or kill the thread (not recommended).
    _save_state_file(_simulators)
    return True

def _export_state(state: dict) -> dict:
    return {k: state.get(k) for k in _DEFAULT_STATE if k != "thread"}


def _simulator_status_json(cp: int | None = None):
    """JSON summary for possible API endpoint / AJAX polling."""
    if cp is not None:
        return json.dumps(_export_state(_simulators[cp]), indent=2)
    return json.dumps({str(idx): _export_state(st) for idx, st in _simulators.items()}, indent=2)

def get_simulator_state(cp: int | None = None, refresh_file: bool = False) -> dict:
    """Return current simulator state, optionally reloading from disk."""
    if refresh_file:
        file_state = _load_state_file()
        for key, val in file_state.items():
            try:
                idx = int(key)
            except ValueError:
                continue
            if idx in _simulators and isinstance(val, dict):
                for k in _DEFAULT_STATE:
                    if k == "thread":
                        continue
                    if k in val:
                        _simulators[idx][k] = val[k]
    # update running flag if the owning process no longer exists
    for st in _simulators.values():
        if st.get("running") and not _pid_alive(st.get("pid")):
            st["running"] = False
    if cp is not None:
        return dict(_simulators[cp])
    return {idx: dict(st) for idx, st in _simulators.items()}

@gw.web.static.include(css=["ocpp/evcs/cp_simulator.css", "/static/tabs.css"], js=["/static/tabs.js"])
def view_cp_simulator(*args, _title="CP Simulator", **kwargs):
    """Web UI for up to two simultaneous simulator sessions."""

    ws_url = gw.web.build_ws_url("ocpp", "csms")
    default_host = ws_url.split("://")[-1].split(":")[0]
    default_ws_port = ws_url.split(":")[-1].split("/")[0] if ":" in ws_url else "9000"
    default_cp_path = {1: "CP1", 2: "CP2"}
    default_rfid = "FFFFFFFF"

    msg = ""
    if request.method == "POST":
        cp_idx = int(request.forms.get("cp") or 1)
        action = request.forms.get("action")
        if action == "start":
            sim_params = dict(
                host=request.forms.get("host") or default_host,
                ws_port=int(request.forms.get("ws_port") or default_ws_port),
                cp_path=request.forms.get("cp_path") or default_cp_path.get(cp_idx, f"CP{cp_idx}"),
                rfid=request.forms.get("rfid") or default_rfid,
                duration=int(request.forms.get("duration") or 600),
                interval=float(request.forms.get("interval") or 5),
                kwh_min=float(request.forms.get("kwh_min") or 30),
                kwh_max=float(request.forms.get("kwh_max") or 60),
                pre_charge_delay=float(request.forms.get("pre_charge_delay") or 0),
                repeat=request.forms.get("repeat") or False,
                daemon=True,
                username=request.forms.get("username") or None,
                password=request.forms.get("password") or None,
            )
            started = _start_simulator(sim_params, cp=cp_idx)
            msg = f"CP{cp_idx} started." if started else f"CP{cp_idx} already running."
        elif action == "stop":
            cp_idx = int(request.forms.get("cp") or 1)
            _stop_simulator(cp=cp_idx)
            msg = f"CP{cp_idx} stop requested."
        else:
            msg = "Unknown action."

    states = {idx: dict(st) for idx, st in _simulators.items()}

    def render_block(cp_idx: int) -> str:
        state = states[cp_idx]
        running = state["running"]
        error = state["last_error"]
        params = state["params"]
        dot_class = "state-dot online" if running else "state-dot stopped"
        dot_label = "Running" if running else "Stopped"

        block = ["<form method='post' class='simulator-form'>"]
        block.append(f"<input type='hidden' name='cp' value='{cp_idx}'>")
        block.append(f"<div><label>Host:</label><input name='host' value='{params.get('host', default_host)}'></div>")
        block.append(f"<div><label>Port:</label><input name='ws_port' value='{params.get('ws_port', default_ws_port)}'></div>")
        block.append(f"<div><label>ChargePoint Path:</label><input name='cp_path' value='{params.get('cp_path', default_cp_path.get(cp_idx, f'CP{cp_idx}'))}'></div>")
        block.append(f"<div><label>RFID:</label><input name='rfid' value='{params.get('rfid', default_rfid)}'></div>")
        block.append(f"<div><label>Duration (s):</label><input name='duration' value='{params.get('duration', 600)}'></div>")
        block.append(f"<div><label>Interval (s):</label><input name='interval' value='{params.get('interval', 5)}'></div>")
        block.append(f"<div><label>Pre-charge Delay (s):</label><input name='pre_charge_delay' value='{params.get('pre_charge_delay', 0)}'></div>")
        block.append(f"<div><label>Energy Min (kWh):</label><input name='kwh_min' value='{params.get('kwh_min', 30)}'></div>")
        block.append(f"<div><label>Energy Max (kWh):</label><input name='kwh_max' value='{params.get('kwh_max', 60)}'></div>")
        block.append("<div><label>Repeat:</label><select name='repeat'>" +
                     f"<option value='False' {'selected' if not params.get('repeat') else ''}>No</option>" +
                     f"<option value='True' {'selected' if str(params.get('repeat')).lower() in ('true','1') else ''}>Yes</option>" +
                     "</select></div>")
        block.append("<div><label>User:</label><input name='username' value=''></div>")
        block.append("<div><label>Pass:</label><input name='password' type='password' value=''></div>")
        block.append("<div class='form-btns'>" +
                     f"<button type='submit' name='action' value='start' {'disabled' if running else ''}>Start</button>" +
                     f"<button type='submit' name='action' value='stop' {'disabled' if not running else ''}>Stop</button>" +
                     "</div>")
        block.append("</form>")
        block.append(f"<div class='simulator-status'><span class='{dot_class}'></span><span>{dot_label}</span></div>")
        block.append("<div class='simulator-details'>" +
                     f"<label>Last Status:</label> <span class='stat'>{state['last_status'] or '-'}</span>" +
                     f"<label>Last Command:</label> <span class='stat'>{state['last_command'] or '-'}</span>" +
                     f"<label>Started:</label> <span class='stat'>{state['start_time'] or '-'}</span>" +
                     f"<label>Stopped:</label> <span class='stat'>{state['stop_time'] or '-'}</span>" +
                     "</div>")
        if error:
            block.append(f"<div class='error'><b>Error:</b><pre>{error}</pre></div>")
        block.append("<details class='simulator-panel'><summary>Show Simulator Params</summary><pre>" +
                     json.dumps(params, indent=2) + "</pre></details>")
        block.append("<details class='simulator-panel'><summary>Show Simulator State JSON</summary><pre>" +
                     _simulator_status_json(cp_idx) + "</pre></details>")
        return "".join(block)

    html = ["<h1>OCPP Charge Point Simulator</h1>"]
    if msg:
        html.append(f"<div class='sim-msg'>{msg}</div>")

    html.append("<div class='gw-tabs'>")
    html.append(
        "<div class='gw-tabs-bar'>"
        "<div class='gw-tab'>Primary CP</div>"
        "<div class='gw-tab'>Secondary CP</div>"
        "</div>"
    )
    html.append(f"<div class='gw-tab-block'>{render_block(1)}</div>")
    html.append(f"<div class='gw-tab-block'>{render_block(2)}</div>")
    html.append("</div>")

    return "".join(html)


def view_simulator(*args, **kwargs):
    """Alias for :func:`view_cp_simulator`."""
    return view_cp_simulator(*args, **kwargs)
