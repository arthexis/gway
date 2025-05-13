from gway import requires, gw
from .apps import setup_app
from .proxies import setup_proxy

# TODO: Create a start_wsgi version that works according to the protocol

@requires("bottle")
def start_server(*,
    host="[WEBSITE_HOST|127.0.0.1]",
    port="[WEBSITE_PORT|8888]",
    debug=False,
    proxy=None,
    app=None,
    daemon=False,
    threaded=True
):
    """Start an HTTP server to host the given application, or the default website if None."""
    from bottle import run

    def run_server():
        gw.info("Building default application")
        actual_app = app or setup_app()
        if proxy:
            actual_app = setup_proxy(endpoint=proxy, app=actual_app)
        gw.info(f"Starting app: {actual_app}")
        run(actual_app, host=host, port=int(port), debug=debug, threaded=threaded)

    if daemon:
        import asyncio
        return asyncio.to_thread(run_server)  # returns coroutine
    else:
        run_server()

