from gway import gw
from .apps import setup_app
from .proxies import setup_proxy


def start_server(*,
    host="[WEBSITE_HOST|127.0.0.1]",
    port="[WEBSITE_PORT|8888]",
    debug=False,
    proxy=None,
    app=None,
    daemon=False,
    threaded=True,
):
    """Start an HTTP or ASGI server to host the given application.

    If `app` is a FastAPI (ASGI) app, runs with Uvicorn.
    If `app` is a WSGI app (Bottle or URLMap or other), uses Paste+ws4py or Bottle.
    """
    def run_server():
        nonlocal app

        # Lazy-load or build the app
        if not app:
            gw.warning(f"Building online help app ({app=}). Run with --app help to remove this warning.")

        if isinstance(app, str):
            app = setup_app(app=app)

        if proxy:
            app = setup_proxy(endpoint=proxy, app=app)

        gw.info(f"Starting app: {app}")

        # Determine if this is an ASGI (FastAPI) application
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
                raise RuntimeError("uvicorn is required to serve ASGI apps. Please install uvicorn.")

            uvicorn.run(
                app,
                host=host,
                port=int(port),
                log_level="debug" if debug else "info",
                workers=1 if not daemon else 0,
            )
        else:
            # Fallback to WSGI
            from bottle import run, Bottle
            from paste import httpserver
            from paste.urlmap import URLMap

            try:
                from ws4py.server.wsgiutils import WebSocketWSGIApplication
                ws4py_available = True
            except ImportError:
                ws4py_available = False

            if ws4py_available or isinstance(app, URLMap):
                httpserver.serve(app, host=host, port=int(port))
            elif isinstance(app, Bottle):
                run(
                    app,
                    host=host,
                    port=int(port),
                    debug=debug,
                    threaded=threaded,
                )
            else:
                raise TypeError(f"Unsupported WSGI app type: {type(app)}")

    if daemon:
        import asyncio
        return asyncio.to_thread(run_server)
    else:
        run_server()
