from gway import gw


def start_server(*,
    host="[WEBSITE_HOST|127.0.0.1]",
    port="[WEBSITE_PORT|8888]",
    debug=False,
    proxy=None,
    app=None,
    daemon=False,
    threaded=True,
):
    """Start an HTTP (WSGI) or ASGI server to host the given application.

    - If `app` is a FastAPI instance, runs with Uvicorn.
    - If `app` is a WSGI app (Bottle, Paste URLMap, or generic WSGI callables), uses Paste+ws4py or Bottle.
    - If `app` is a zero-arg factory, it will be invoked (supporting sync or async factories).
    """
    import inspect
    import asyncio

    def run_server():
        nonlocal app

        # 1. Lazy-load or build the app from a string or None
        if app is None or isinstance(app, str):
            if app is None:
                gw.warning(
                    f"Building online help app (app=None). Run with --app help to remove this warning."
                )
            from .apps import setup_app
            app = setup_app(app=app)

        # 2. Wrap with proxy if requested
        if proxy:
            from .proxies import setup_proxy
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
                # It's a WSGI/ASGI callable; do not invoke
                gw.info(f"Detected callable WSGI/ASGI app: {app}")

        gw.info(f"Starting {app=} @ {host}:{port}")

        # 4. Detect ASGI/FastAPI
        try:
            from fastapi import FastAPI
            is_asgi = isinstance(app, FastAPI)
        except ImportError:
            is_asgi = False

        if is_asgi:
            # Run ASGI app with Uvicorn
            try:
                import uvicorn
            except ImportError:
                raise RuntimeError(
                    "uvicorn is required to serve ASGI apps. Please install uvicorn."
                )

            uvicorn.run(
                app,
                host=host,
                port=int(port),
                log_level="debug" if debug else "info",
                workers=1,
                reload=debug,
            )
            return  # done

        # 5. Fallback to WSGI servers
        from bottle import run as bottle_run, Bottle
        try:
            from paste import httpserver
            from paste.urlmap import URLMap
        except ImportError:
            httpserver = None
            URLMap = None

        try:
            from ws4py.server.wsgiutils import WebSocketWSGIApplication
            ws4py_available = True
        except ImportError:
            ws4py_available = False

        # a) Paste HTTP server (supports any WSGI callable)
        if httpserver:
            # use Paste+ws4py if websockets, otherwise generic WSGI serve
            httpserver.serve(app, host=host, port=int(port))
        # b) Fallback to Bottle run for Bottle apps
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

    # 6. Daemon mode: run in a background thread
    if daemon:
        return asyncio.to_thread(run_server)
    else:
        run_server()
