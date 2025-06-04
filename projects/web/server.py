from numpy import iterable
from gway import gw

# TODO: Add a --reload option for web servers that support development mode reload
# if True, enable default reload settings. Reload can also take a folder to watch over
# of a list of comma-separated folders if the backend supports it.
# You can find the path to each with gw.resource(folder)

def start(*,
    host="[WEBSITE_HOST|127.0.0.1]",
    port="[WEBSITE_PORT|8888]",
    debug=False,
    proxy=None,
    app=None,
    daemon=False,
    threaded=True,
    is_worker=False,
):
    """Start an HTTP (WSGI) or ASGI server to host the given application.

    - If `app` is a FastAPI instance, runs with Uvicorn.
    - If `app` is a WSGI app (Bottle, Paste URLMap, or generic WSGI callables), uses Paste+ws4py or Bottle.
    - If `app` is a zero-arg factory, it will be invoked (supporting sync or async factories).
    - If `app` is a list of apps, each will be run in its own thread (each on an incremented port).
    """
    import inspect
    import asyncio

    # TODO: Make sure that all apps run when multiple apps are provided. 
    # Print the total number of started apps and their types.

    def run_server():
        nonlocal app
        all_apps = app if iterable(app) else (app, )

        # B. Dispatch multiple apps in threads if we aren't already in a worker
        if not is_worker and len(all_apps) > 1:
            from threading import Thread
            threads = []
            gw.info(f"Starting {len(all_apps)} apps in parallel threads.")
            for i, sub_app in enumerate(all_apps):
                try:
                    from fastapi import FastAPI
                    app_type = "FastAPI" if isinstance(sub_app, FastAPI) else type(sub_app).__name__
                except ImportError:
                    app_type = type(sub_app).__name__
                gw.info(f"  App {i+1}: type={app_type}, port={int(port) + i}")

                t = Thread(
                    target=gw.web.server.start,
                    kwargs=dict(
                        host=host,
                        port=int(port) + i,
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
            if not daemon:
                for t in threads:
                    t.join()
            return

        # 1. If no apps passed, fallback to default app
        if not all_apps:
            gw.warning(
                "Building default app (app is None). Run with --app default to silence.")
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
            try:
                import uvicorn
            except ImportError:
                raise RuntimeError("uvicorn is required to serve ASGI apps. Please install uvicorn.")

            uvicorn.run(
                app,
                host=host,
                port=int(port),
                log_level="debug" if debug else "info",
                workers=1,
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
            httpserver.serve(app, host=host, port=int(port))
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


start_app = start
