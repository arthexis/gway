from gway import requires, gw


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

