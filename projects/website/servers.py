from gway import requires, gw
from .apps import setup_app



@requires("bottle", "requests")
def setup_proxy(*, endpoint : str, app=None, websockets=False):
    """
    Create a proxy handler to the given Bottle app.
    When using this proxy, attach/create this proxy first then attach the rest of your routes.
    Otherwise, the proxy will catch all requests and block other routes.
    """
    from bottle import request, Bottle
    import requests

    # TODO: Implement websocket forwarding if websockets=True
    # This should be transparent to websocket applications, including authentication

    if app is None: app = Bottle()

    @app.route("/<path:path>", method=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
    def proxy_handler(path):
        target_url = f"{endpoint.rstrip('/')}/{path}"
        headers = {key: value for key, value in request.headers.items()}
        method = request.method
        try:
            resp = requests.request(method, target_url, headers=headers, data=request.body.read(), stream=True)
            return resp.content, resp.status_code, resp.headers.items()
        except Exception as e:
            gw.error("Proxy request failed: %s", e)
            return f"Proxy error: {e}", 502


@requires("bottle")
def start_server(*,
    host="[WEBSITE_HOST|127.0.0.1]",
    port="[WEBSITE_PORT|8888]",
    debug=False,
    proxy=None,
    app=None,
    daemon=False  # this is the trigger
):
    """Start an HTTP server to host the given application, or the default website if None."""
    from bottle import run

    def run_server():
        gw.info("Building default application")
        actual_app = app or setup_app()
        if proxy:
            actual_app = setup_proxy(endpoint=proxy, app=actual_app)
        gw.info(f"Starting app: {actual_app}")
        run(actual_app, host=host, port=int(port), debug=debug)

    if daemon:
        import asyncio
        return asyncio.to_thread(run_server)  # returns coroutine
    else:
        run_server()

