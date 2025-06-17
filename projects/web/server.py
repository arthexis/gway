# projects/web/server.py

from numpy import iterable
from gway import gw

_default_app_build_count = 0

def start_app(*,
    host="[WEBSITE_HOST|127.0.0.1]",
    port="[WEBSITE_PORT|8888]",
    ws_port="[WEBSOCKETS_PORT|9000]",         
    debug=False,
    proxy=None,
    app=None,
    daemon=True,
    threaded=True,
    is_worker=False,
    workers=None,
):
    """
    Start an HTTP (WSGI) or ASGI server to host the given application.

    - If `app` is a FastAPI instance, runs with Uvicorn (optionally on ws_port if set).
    - If `app` is a WSGI app, uses Paste+ws4py or Bottle.
    - If `app` is a zero-arg factory, it will be invoked (supporting sync or async factories).
    - If `app` is a list of apps, each will be run in its own thread (each on an incremented port; FastAPI uses ws_port if set).
    """
    import inspect
    import asyncio

    host = gw.resolve(host) if isinstance(host, str) else host
    port = gw.resolve(port) if isinstance(port, str) else port
    ws_port = gw.resolve(ws_port) if isinstance(ws_port, str) else ws_port

    def run_server():
        nonlocal app
        all_apps = app if iterable(app) else (app, )

        # ---- Multi-app mode ----
        if not is_worker and len(all_apps) > 1:
            from threading import Thread
            from collections import Counter
            threads = []
            app_types = []
            gw.info(f"Starting {len(all_apps)} apps in parallel threads.")

            fastapi_count = 0
            for i, sub_app in enumerate(all_apps):
                try:
                    from fastapi import FastAPI
                    is_fastapi = isinstance(sub_app, FastAPI)
                    app_type = "FastAPI" if is_fastapi else type(sub_app).__name__
                except ImportError:
                    is_fastapi = False
                    app_type = type(sub_app).__name__

                # ---- Use ws_port for the first FastAPI app if provided, else increment port as before ----
                if is_fastapi and ws_port and fastapi_count == 0:
                    port_i = int(ws_port)
                    fastapi_count += 1
                else:
                    # Use base port + i, skipping ws_port if it's in the range
                    port_i = int(port) + i
                    # Prevent port collision if ws_port == port_i (rare but possible)
                    if ws_port and port_i == int(ws_port):
                        port_i += 1

                gw.info(f"  App {i+1}: type={app_type}, port={port_i}")
                app_types.append(app_type)

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
                    ),
                    daemon=daemon,
                )
                t.start()
                threads.append(t)

            type_summary = Counter(app_types)
            summary_str = ", ".join(f"{count}×{t}" for t, count in type_summary.items())
            gw.info(f"All {len(all_apps)} apps started. Types: {summary_str}")

            if not daemon:
                for t in threads:
                    t.join()
            return

        # ---- Single-app mode ----
        global _default_app_build_count
        if not all_apps or all_apps == (None,):
            _default_app_build_count += 1
            if _default_app_build_count > 1:
                gw.warning(
                    f"Default app is being built {_default_app_build_count} times! "
                    "This may indicate a misconfiguration or repeated server setup. "
                    "Check your recipe/config. Run with --app default to silence."
                )
            app = gw.web.app.setup(app=None)
        else:
            app = all_apps[0]

        # Proxy setup (unchanged)
        if proxy:
            from .proxy import setup_app as setup_proxy
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
            is_asgi = isinstance(app, FastAPI)
        except ImportError:
            is_asgi = False

        if is_asgi:
            # Use ws_port if provided, else use regular port
            port_to_use = int(ws_port) if ws_port else int(port)
            ws_url = f"ws://{host}:{port_to_use}"
            gw.info(f"WebSocket support active @ {ws_url}/<path>?token=...")
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
                reload=debug,
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

        if httpserver:
            httpserver.serve(
                app, host=host, port=int(port), 
                threadpool_workers=(workers or 5), 
            )
        elif isinstance(app, Bottle):
            bottle_run(
                app,
                host=host,
                port=int(port),
                debug=debug,
                threaded=threaded,
            )
        else:
            raise TypeError(f"Unsupported WSGI app type: {type(app)}")

    if daemon:
        return asyncio.to_thread(run_server)
    else:
        run_server()
