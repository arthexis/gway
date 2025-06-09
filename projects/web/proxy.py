# projects/web/proxy.py

from fastapi import FastAPI
from gway import gw
import requests

# TODO: Test that setup_fallback_app will work with our OCPP apps.


def setup_fallback_app(*, 
        endpoint: str, app=None, websockets: bool = False, path: str = "/",
        mode: str = "extend", callback=None,
    ):
    """
    Create an HTTP (and optional WebSocket) fallback to the given endpoint.
    This asumes the given endpoint will replicate or provide missing functionality
    or the entire service if it can't be provided locally. 
    """
    # selectors for app types
    from bottle import Bottle

    # TODO: Implement a mode kwarg that defaults to "extend" and functions like this:
    # replace: Replace all paths in the received apps with the proxied endpoint.
    # extend: Redirect all paths not already configured to the proxy.
    # errors: Catch errors thrown by the app and redirect the failed calls to the proxy.
    # trigger: Use a callback function to check. Redirects when result is True.
    # Move this explanation to the docstring.

    # TODO: We need to use gw.unwrap_all instead and apply the proxy mode to each of the
    #       apps found there, then we need to return all those apps in a collection.

    # collect apps by type
    bottle_app = gw.unwrap_one(app, Bottle)
    fastapi_app = gw.unwrap_one(app, FastAPI)

    prepared = []

    # if no matching apps, default to a new Bottle
    if not bottle_app and not fastapi_app:
        default = Bottle()
        prepared.append(_wire_proxy(default, endpoint, websockets, path))
    elif bottle_app:
        prepared.append(_wire_proxy(bottle_app, endpoint, websockets, path))
    elif fastapi_app:
        prepared.append(_wire_proxy(fastapi_app, endpoint, websockets, path))

    # TODO: Test that this return is properly compatible with web.server.start_app after the fixes

    return prepared[0] if len(prepared) == 1 else tuple(prepared)


def _wire_proxy(app, endpoint: str, websockets: bool, path: str):
    """
    Internal: attach HTTP and optional WS proxy routes
    to Bottle or FastAPI-compatible app. Both content and headers are proxied.
    """
    # detect FastAPI-like
    is_fastapi = hasattr(app, "websocket")

    # auto-enable websockets for FastAPI
    if is_fastapi and not websockets:
        websockets = True

    # FastAPI: new app if needed
    if app is None and websockets:
        from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
        import httpx, websockets, asyncio

        app = FastAPI()
        base = path.rstrip("/") or "/"

        @app.api_route(f"{base}/{{full_path:path}}", methods=["GET","POST","PUT","PATCH","DELETE","OPTIONS","HEAD"])
        async def proxy_http(request: Request, full_path: str):
            url = endpoint.rstrip("/") + "/" + full_path
            client = httpx.AsyncClient()
            headers = dict(request.headers)
            body = await request.body()
            resp = await client.request(request.method, url, headers=headers, content=body)
            return resp.content, resp.status_code, resp.headers.items()

        @app.websocket(f"{base}/{{full_path:path}}")
        async def proxy_ws(ws: WebSocket, full_path: str):
            upstream = endpoint.rstrip("/") + "/" + full_path
            await ws.accept()
            try:
                async with websockets.connect(upstream) as up:
                    async def c2u():
                        while True:
                            m = await ws.receive_text()
                            await up.send(m)
                    async def u2c():
                        while True:
                            m = await up.recv()
                            await ws.send_text(m)
                    await asyncio.gather(c2u(), u2c())
            except WebSocketDisconnect:
                pass
            except Exception as e:
                gw.error(f"WebSocket proxy error: {e}")

        return app

    # Bottle-only HTTP proxy
    if hasattr(app, "route") and not is_fastapi:
        from bottle import request

        @app.route(f"{path}<path:path>", method=["GET","POST","PUT","DELETE","PATCH","OPTIONS","HEAD"])
        def _bottle_proxy(path):
            target = f"{endpoint.rstrip('/')}/{path}"
            headers = {k: v for k, v in request.headers.items()}
            try:
                resp = requests.request(request.method, target, headers=headers, data=request.body.read(), stream=True)
                return resp.content, resp.status_code, resp.headers.items()
            except Exception as e:
                gw.error("Proxy request failed: %s", e)
                return f"Proxy error: {e}", 502

        if websockets:
            gw.warning("WebSocket proxy requested but Bottle does not support WebSockets; ignoring websockets=True")

        return app

    # Existing FastAPI-like app augmentation
    if is_fastapi:
        from fastapi import WebSocket, WebSocketDisconnect, Request
        import httpx, websockets, asyncio

        base = path.rstrip("/") or "/"

        @app.api_route(f"{base}/{{full_path:path}}", methods=["GET","POST","PUT","PATCH","DELETE","OPTIONS","HEAD"])
        async def proxy_http(request: Request, full_path: str):
            url = endpoint.rstrip("/") + "/" + full_path
            client = httpx.AsyncClient()
            headers = dict(request.headers)
            body = await request.body()
            resp = await client.request(request.method, url, headers=headers, content=body)
            return resp.content, resp.status_code, resp.headers.items()

        if websockets:
            @app.websocket(f"{base}/{{full_path:path}}")
            async def proxy_ws(ws: WebSocket, full_path: str):
                upstream = endpoint.rstrip("/") + "/" + full_path
                await ws.accept()
                try:
                    async with websockets.connect(upstream) as up:
                        async def c2u():
                            while True:
                                m = await ws.receive_text()
                                await up.send(m)
                        async def u2c():
                            while True:
                                m = await up.recv()
                                await ws.send_text(m)
                        await asyncio.gather(c2u(), u2c())
                except WebSocketDisconnect:
                    pass
                except Exception as e:
                    gw.error(f"WebSocket proxy error: {e}")

        return app

    raise RuntimeError("Unsupported app type for setup_proxy: must be Bottle or FastAPI-compatible")
