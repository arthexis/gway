# file: projects/monitor/monitor.py

import time
import datetime
import asyncio
from gway import gw

NETWORK_STATE = {}         # {project: {last_run, last_result, ...}}
MONITOR_NEXT_CHECK = {}    # {project: next_check_iso}
MONITOR_TRIGGER = {}       # {project: asyncio.Event (optional)}
MONITOR_RENDER = {}        # {project: list of renderers}

def now_iso():
    """Return current time as ISO8601 string (seconds precision)."""
    return datetime.datetime.now().isoformat(timespec="seconds")

def get_state(project):
    """Return the state dict for the given project, creating it if needed."""
    project = str(project)
    return NETWORK_STATE.setdefault(project, {})

def set_state(project, key, value):
    """Set a single key/value in the state for a given project."""
    get_state(project)[key] = value

def set_states(project, mapping):
    """Set multiple key/values in the state for a given project."""
    get_state(project).update(mapping)

def get_next_check_time(project):
    """Get the next scheduled check time for a given project (ISO8601 or None)."""
    return MONITOR_NEXT_CHECK.get(project)

def trigger_watch(project):
    """Trigger an immediate check for a given project, if async Event is set up."""
    trig = MONITOR_TRIGGER.get(project)
    if trig and hasattr(trig, "set"):
        trig.set()
        return True
    return False

def start_watch(
    project, *,
    monitor=None,
    interval=120,
    delay=0,
    block=False,
    daemon=True,
    render=None,
    logger=None,
    **kwargs
):
    """
    Start a watcher loop for a project.
      - project: Name of the GWAY project or subproject.
      - monitor: Name or list of monitor functions (string or list, without prefix).
      - interval: Minimum seconds between checks. CLI users may also specify
        ``--seconds``, ``--minutes``, ``--hours`` or ``--days`` which are
        converted automatically.
      - delay: Startup delay (seconds).
      - block: Block main thread? (default False)
      - daemon: Async coroutine? (default True)
      - render: Name or list of render functions (without prefix), for dashboard.
      - logger: Optional logger (uses print if not provided).
      - kwargs: Extra parameters for monitor functions.
    """
    global MONITOR_NEXT_CHECK, MONITOR_TRIGGER, MONITOR_RENDER

    project_name = str(project)
    log_prefix = f"[monitor:{project_name}] "

    gproj = gw.find_project(f"monitor.{project_name}")
    if not gproj:
        raise ValueError(f"{log_prefix}Project not found in GWAY: 'monitor.{project_name}'")

    # Select monitors (function names)
    monitors = gw.cast.to_list(monitor) if monitor else [project_name]
    monitor_funcs = []
    for mname in monitors:
        funcname = f"monitor_{mname}"
        func = getattr(gproj, funcname, None)
        if not func:
            raise ValueError(f"{log_prefix}Monitor function '{funcname}' not found in project '{project_name}'.")
        monitor_funcs.append((funcname, func))

    # Set up renders for this project (for dashboard view)
    if render is not None:
        renders = gw.cast.to_list(render)
        MONITOR_RENDER[project_name] = renders
    elif project_name not in MONITOR_RENDER:
        MONITOR_RENDER[project_name] = [project_name]

    def log_info(msg):
        if logger: logger.info(msg)
        else: print(f"{log_prefix}{msg}")

    def log_warn(msg):
        if logger: logger.warning(msg)
        else: print(f"{log_prefix}[WARN] {msg}")

    trig = None

    async def async_loop():
        """Async watcher loop (recommended for web/production)."""
        nonlocal trig
        if delay > 0:
            log_info(f"Waiting {delay}s before starting monitor loop...")
            await asyncio.sleep(delay)
        trig = MONITOR_TRIGGER.setdefault(project_name, asyncio.Event())
        while True:
            state = get_state(project_name)
            state["last_run"] = now_iso()
            state["last_result"] = results = []
            for funcname, func in monitor_funcs:
                try:
                    log_info(f"Calling {funcname} ...")
                    result = func(**kwargs)
                    results.append((funcname, result))
                except Exception as e:
                    log_warn(f"Exception in {funcname}: {e}")
                    results.append((funcname, f"error: {e}"))
            next_time = datetime.datetime.now() + datetime.timedelta(seconds=interval)
            MONITOR_NEXT_CHECK[project_name] = next_time.isoformat(timespec="seconds")
            try:
                await asyncio.wait_for(trig.wait(), timeout=interval)
                trig.clear()
                log_info("Triggered immediate check via trigger_watch.")
            except asyncio.TimeoutError:
                pass

    def blocking_loop():
        """Synchronous watcher loop (for legacy CLI or quick tests)."""
        if delay > 0:
            log_info(f"Waiting {delay}s before starting monitor loop...")
            time.sleep(delay)
        while True:
            state = get_state(project_name)
            state["last_run"] = now_iso()
            state["last_result"] = results = []
            for funcname, func in monitor_funcs:
                try:
                    log_info(f"Calling {funcname} ...")
                    result = func(**kwargs)
                    results.append((funcname, result))
                except Exception as e:
                    log_warn(f"Exception in {funcname}: {e}")
                    results.append((funcname, f"error: {e}"))
            next_time = datetime.datetime.now() + datetime.timedelta(seconds=interval)
            MONITOR_NEXT_CHECK[project_name] = next_time.isoformat(timespec="seconds")
            time.sleep(interval)

    # Main entry points
    if daemon:
        return async_loop()
    if block:
        blocking_loop()
    else:
        state = get_state(project_name)
        state["last_run"] = now_iso()
        state["last_result"] = results = []
        for funcname, func in monitor_funcs:
            try:
                log_info(f"Calling {funcname} ...")
                result = func(**kwargs)
                results.append((funcname, result))
            except Exception as e:
                log_warn(f"Exception in {funcname}: {e}")
                results.append((funcname, f"error: {e}"))
        next_time = datetime.datetime.now() + datetime.timedelta(seconds=interval)
        MONITOR_NEXT_CHECK[project_name] = next_time.isoformat(timespec="seconds")
        return results

def view_monitor_panel(**_):
    """
    Dashboard view: Displays current state and HTML reports for each configured monitor.
    Each monitor section is rendered by calling the specified render function(s) in the project:
      - render_<render> for each render in MONITOR_RENDER[project]
      - fallback: render_<project> or render_monitor
    Below the monitor, display last run and next scheduled run.
    """
    html = ['<div class="gway-net-dashboard">']
    if not NETWORK_STATE:
        html.append('<div class="warn" style="color:#a00;">No monitors are currently running.</div>')
    for project in NETWORK_STATE:
        state = get_state(project)
        html.append(f'<div class="monitor-block">')
        gproj = gw.find_project(f"monitor.{project}")
        renders = MONITOR_RENDER.get(project) or [project]
        rendered = False
        for rname in renders:
            funcname = f"render_{rname}"
            func = getattr(gproj, funcname, None)
            if func:
                try:
                    frag = func()
                    html.append(f'<div class="monitor-frag">{frag}</div>')
                    rendered = True
                except Exception as e:
                    html.append(f'<div class="error">Error in {funcname}: {e}</div>')
        if not rendered:
            for fallback in [f"render_{project}", "render_monitor"]:
                func = getattr(gproj, fallback, None)
                if func:
                    try:
                        frag = func()
                        html.append(f'<div class="monitor-frag">{frag}</div>')
                        rendered = True
                        break
                    except Exception as e:
                        html.append(f'<div class="error">Error in {fallback}: {e}</div>')
        if not rendered:
            html.append('<div class="no-render" style="color:#888;">No render function found for this monitor.</div>')
        # Show info about last run and next run
        last_run = state.get("last_run") or "-"
        next_run = get_next_check_time(project) or "-"
        html.append(f'<div class="monitor-meta" style="margin-top:7px;font-size:90%;color:#888;">'
                    f'Last run: <b>{last_run}</b> | Next check: <b>{next_run}</b></div>')
        html.append('</div>')
    html.append('</div>')
    return '\n'.join(html)
