# projects/web/server.py

# This project supports starting apps using a local server, but also handles
# the administration of external web servers in one single package.

from numpy import iterable
from gway import gw

# TODO: Ensure start_app is compatible with applications that use websocket endpoints
# such as ocpp.setup_csms_v16_app. The ws:// URL should be logged and printed to
# the console the same way the http:// URL is displayed.

def start_app(*,
    host="[WEBSITE_HOST|127.0.0.1]",
    port="[WEBSITE_PORT|8888]",
    debug=False,
    proxy=None,
    app=None,
    daemon=True,
    threaded=True,
    is_worker=False,
    workers=None,
):
    """Start an HTTP (WSGI) or ASGI server to host the given application.

    - If `app` is a FastAPI instance, runs with Uvicorn.
    - If `app` is a WSGI app (Bottle, Paste URLMap, or generic WSGI callables), uses Paste+ws4py or Bottle.
    - If `app` is a zero-arg factory, it will be invoked (supporting sync or async factories).
    - If `app` is a list of apps, each will be run in its own thread (each on an incremented port).
    """
    import inspect
    import asyncio

    def run_server():
        nonlocal app
        all_apps = app if iterable(app) else (app, )

        # B. Dispatch multiple apps in threads if we aren't already in a worker
        if not is_worker and len(all_apps) > 1:
            from threading import Thread
            from collections import Counter
            threads = []
            app_types = []
            gw.info(f"Starting {len(all_apps)} apps in parallel threads.")
            for i, sub_app in enumerate(all_apps):
                try:
                    from fastapi import FastAPI
                    app_type = "FastAPI" if isinstance(sub_app, FastAPI) else type(sub_app).__name__
                except ImportError:
                    app_type = type(sub_app).__name__
                port_i = int(port) + i
                gw.info(f"  App {i+1}: type={app_type}, port={port_i}")
                app_types.append(app_type)

                t = Thread(
                    target=gw.web.server.start_app,
                    kwargs=dict(
                        host=host,
                        port=port_i,
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

        # 1. If no apps passed, fallback to default app
        if not all_apps:
            # TODO: Only show this warning if the default app is being built twice which may indicate
            #       and error in the configuration or recipe. Building it once is not a warning.
            gw.warning("Building default app (app is None). Run with --app default to silence.")
            app = gw.web.app.setup(app=None)
        else:
            app = all_apps[0]  # Run the first (or only) app normally

        # 2. Wrap with proxy if requested
        if proxy:
            from .proxy import setup_app as setup_proxy
            app = setup_proxy(endpoint=proxy, app=app)

        # 3. If app is a zero-arg factory, invoke it
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

        gw.info(f"Starting {app=} @ {host}:{port}")

        # 4. Detect ASGI/FastAPI
        try:
            from fastapi import FastAPI
            is_asgi = isinstance(app, FastAPI)
        except ImportError:
            is_asgi = False

        if is_asgi:
            ws_url = f"ws://{host}:{port}"
            gw.info(f"WebSocket support active @ {ws_url}/<path>?token=...")
            try:
                import uvicorn
            except ImportError:
                raise RuntimeError("uvicorn is required to serve ASGI apps. Please install uvicorn.")

            uvicorn.run(
                app,
                host=host,
                port=int(port),
                log_level="debug" if debug else "info",
                workers=workers or 1,
                reload=debug,
            )
            return

        # 5. Fallback to WSGI servers
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
