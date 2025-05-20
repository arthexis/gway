from gway import gw
from .apps import setup_app
from .proxies import setup_proxy

try:
    # Check for ws4py availability
    from ws4py.server.wsgiutils import WebSocketWSGIApplication as _
    ws4py_available = True
except ImportError:
    ws4py_available = False


def start_server(*,
    host="[WEBSITE_HOST|127.0.0.1]",
    port="[WEBSITE_PORT|8888]",
    debug=False,
    proxy=None,
    app=None,
    daemon=False,
    threaded=True,
):
    """Start an HTTP server to host the given application, or the base help website if None.

    If ws4py is installed and any WebSocket routes are mounted, uses Paste+ws4py.
    Otherwise falls back to the default Bottle server.
    """
    from bottle import run
    from paste import httpserver

    def run_server():
        nonlocal app
        # Build base app if none provided
        if not app:
            gw.warning(f"Building online help app ({app=}). Run with --app help to remove this warning.")
            gw.warning("You may also get this warning if your app factory is not compatible with bottle.run()")
        if isinstance(app, str):
            app = setup_app(app=app)

        # Apply proxy if requested
        if proxy:
            app = setup_proxy(endpoint=proxy, app=app)

        gw.info(f"Starting app: {app}")

        # Choose server based on ws4py availability
        if ws4py_available:
            # Paste httpserver will dispatch to ws4py-mounted routes automatically
            httpserver.serve(app, host=host, port=int(port))
        else:
            run(app,
                host=host,
                port=int(port),
                debug=debug,
                threaded=threaded,
                )

    if daemon:
        import asyncio
        return asyncio.to_thread(run_server)
    else:
        run_server()
