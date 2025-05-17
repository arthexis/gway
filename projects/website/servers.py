from gway import requires, gw
from .apps import setup_app
from .proxies import setup_proxy


@requires("bottle")
def start_server(*,
    host="[WEBSITE_HOST|127.0.0.1]",
    port="[WEBSITE_PORT|8888]",
    debug=False,
    proxy=None,
    app=None,
    daemon=False,
    threaded=True,
    default=False,
):
    """Start an HTTP server to host the given application, or the default help website if None."""
    from bottle import run

    def run_server():
        nonlocal default, app
        if not app:
            if not default:
                gw.warning("Building default help app. If this was your intent, run with --default.")
            app = setup_app()
        if proxy:
            app = setup_proxy(endpoint=proxy, app=app)
        gw.info(f"Starting app: {app}")
        run(app, host=host, port=int(port), debug=debug, threaded=threaded)

    if daemon:
        import asyncio
        return asyncio.to_thread(run_server)  # returns coroutine
    else:
        run_server()

