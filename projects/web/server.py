# file: projects/web/server.py

import socket
from gway import gw, __

# Registry for active apps and their hosts/ports
_active_servers = {}  # key: label or index, value: dict with host/port/ws_port

def start_app(*,
    host            = __('[SITE_HOST]', '[BASE_HOST]', '0.0.0.0'),
    port : int      = __('[SITE_PORT]', '[BASE_PORT]', '8888'),
    ws_port : int   = __('[WS_PORT]', '[WEBSOCKET_PORT]', '9999'),
    debug=False,
    proxy=None,
    app=None,
    daemon=True,
    threaded=True,
    is_worker=False,
    workers=None,
    label=None,  # for multi-app registry
):
    import inspect
    import asyncio

    global _active_servers

    def run_server(app_label=None):
        nonlocal app
        match app:
            case list() | tuple() as seq:
                all_apps = tuple(seq)
            case None:
                all_apps = (None,)
            case _:
                all_apps = (app,)

        # ---- Multi-app mode ----
        if not is_worker and len(all_apps) > 1:
            from threading import Thread
            from collections import Counter
            threads = []
            app_types = []
            gw.info(f"Starting {len(all_apps)} apps in parallel threads.")

            fastapi_count = 0
            try:
                from fastapi import FastAPI
            except ImportError:
                FastAPI = None

            for i, sub_app in enumerate(all_apps):
                match sub_app:
                    case _ if FastAPI and isinstance(sub_app, FastAPI):
                        is_fastapi = True
                        app_type = "FastAPI"
                    case _:
                        is_fastapi = False
                        app_type = type(sub_app).__name__

                # ---- Use ws_port for the first FastAPI app if provided, else increment port as before ----
                if is_fastapi and ws_port and fastapi_count == 0:
                    port_i = ws_port
                    fastapi_count += 1
                else:
                    port_i = port + i
                    if ws_port and port_i == ws_port:
                        port_i += 1

                # --- Register server info BEFORE thread starts ---
                label_i = app_type.lower() if is_fastapi else f"wsgi{i+1}"
                if i == 0:
                    label_i = "main"
                _active_servers[label_i] = dict(host=host, port=port_i, ws_port=ws_port if is_fastapi else None)

                gw.info(f"  App {i+1}: type={app_type}, port={port_i}")

                t = Thread(
                    target=gw.web.server.start_app,
                    kwargs=dict(
                        host=host,
                        port=port_i,
                        ws_port=None,  # Only outer thread assigns ws_port!
                        debug=debug,
                        proxy=proxy,
                        app=sub_app,
                        daemon=daemon,
                        threaded=threaded,
                        is_worker=True,
                        label=label_i,
                    ),
                    daemon=daemon,
                )
                t.start()
                threads.append(t)
                app_types.append(app_type)

            type_summary = Counter(app_types)
            summary_str = ", ".join(f"{count}×{t}" for t, count in type_summary.items())
            gw.info(f"All {len(all_apps)} apps started. Types: {summary_str}")

            if not daemon:
                for t in threads:
                    t.join()
            return

        # ---- Single-app mode ----
        if not app:
            raise NotImplementedError("No app received. Auto-build mode has been phased out.")

        # Proxy setup (unchanged)
        if proxy:
            setup_proxy = gw.web.proxy.fallback_app
            app = setup_proxy(endpoint=proxy, app=app)

        # Factory support (unchanged)
        if callable(app):
            sig = inspect.signature(app)
            if len(sig.parameters) == 0:
                gw.info(f"Calling app factory: {app}")
                maybe_app = app()
                if inspect.isawaitable(maybe_app):
                    maybe_app = asyncio.get_event_loop().run_until_complete(maybe_app)
                app = maybe_app
            else:
                gw.info(f"Detected callable WSGI/ASGI app: {app}")

        # ---- Detect ASGI/FastAPI ----
        try:
            from fastapi import FastAPI
        except ImportError:
            FastAPI = None

        match app:
            case _ if FastAPI and isinstance(app, FastAPI):
                is_asgi = True
            case _:
                is_asgi = False

        if is_asgi:
            # Use ws_port if provided, else use regular port
            port_to_use = ws_port if ws_port else port
            ws_url = f"ws://{host}:{port_to_use}"
            gw.info(f"WebSocket support active @ {ws_url}/<path>?token=...")

            # --- Register server info ---
            reg_label = label or "main"
            _active_servers[reg_label] = dict(host=host, port=port, ws_port=ws_port)
            gw.info(f"[asgi] Registered app servers: {all_app_servers()}")

            try:
                import uvicorn
            except ImportError:
                raise RuntimeError("uvicorn is required to serve ASGI apps. Please install uvicorn.")

            uvicorn.run(
                app,
                host=host,
                port=port_to_use,
                log_level="debug" if debug else "info",
                workers=workers or 1,
                reload=False,
            )
            return

        # ---- WSGI fallback (unchanged) ----
        from bottle import run as bottle_run, Bottle
        try:
            from paste import httpserver
        except ImportError:
            httpserver = None

        try:
            from ws4py.server.wsgiutils import WebSocketWSGIApplication
            ws4py_available = True
        except ImportError:
            ws4py_available = False

        # --- Register server info ---
        reg_label = label or "main"
        _active_servers[reg_label] = dict(host=host, port=port, ws_port=None)
        gw.info(f"[wsgi] Registered app servers: {all_app_servers()}")

        if httpserver:
            httpserver.serve(
                app, host=host, port=port, 
                threadpool_workers=(workers or 5), 
            )
        elif isinstance(app, Bottle):
            bottle_run(
                app,
                host=host,
                port=port,
                debug=debug,
                threaded=threaded,
            )
        else:
            raise TypeError(f"Unsupported WSGI app type: {type(app)}")

    if daemon:
        return asyncio.to_thread(run_server)
    else:
        run_server()

# === App host/port tracking ===

def app_host(label="main"):
    """
    Return the actual host (interface/address) currently used by the running web server.
    By default, returns the primary (first) app's host.
    For multi-app mode, use label="main" or label="fastapi", etc.
    """
    host = _active_servers.get(label, {}).get("host")
    return host if host != '0.0.0.0' else '127.0.0.1'

def app_port(label="main"):
    """
    Return the actual port used by the main web server instance.
    For multi-app, use label as above.
    """
    return _active_servers.get(label, {}).get("port")

def app_ws_port(label="main"):
    """
    Return the port used for WebSocket/ASGI FastAPI, if any (else None).
    For multi-app, use label as above.
    """
    return _active_servers.get(label, {}).get("ws_port")

def all_app_servers():
    """
    Returns dict of all known app servers (label => info).
    """
    return dict(_active_servers)

def is_local(request=None, host=None):
    """
    Returns True if the active HTTP request originates from the same machine
    that the server is running on (i.e., local request). Supports FastAPI and Bottle (ASGI/WSGI).
    """
    try:
        if request is None:
            try:
                from starlette.requests import Request as StarletteRequest
                import contextvars
                req_var = contextvars.ContextVar("request")
                request = req_var.get()
            except Exception:
                pass
            if request is None:
                try:
                    from bottle import request as bottle_request
                    request = bottle_request
                except ImportError:
                    request = None

        remote_addr = None
        if request is not None:
            remote_addr = getattr(getattr(request, "client", None), "host", None)
            if not remote_addr:
                remote_addr = getattr(request, "remote_addr", None)
            if not remote_addr and hasattr(request, "environ"):
                remote_addr = request.environ.get("REMOTE_ADDR")
        else:
            return False

        # Use the tracked app host if available
        if host is None:
            host = app_host() or gw.web.host()
        if not host or host in ("0.0.0.0", "::", ""):
            return False

        def _norm(addr):
            if addr in ("localhost",):
                return "127.0.0.1"
            if addr in ("::1",):
                return "127.0.0.1"
            try:
                return socket.gethostbyname(addr)
            except Exception:
                return addr

        remote_ip = _norm(remote_addr)
        host_ip = _norm(host)
        return remote_ip.startswith("127.") or remote_ip == host_ip
    except Exception as ex:
        import traceback
        print(f"[is_local] error: {ex}\n{traceback.format_exc()}")
        return False
