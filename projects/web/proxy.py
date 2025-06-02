# projects/web/proxy.py

from gway import gw
import requests


def setup_app(*apps, endpoint: str, app=None, websockets: bool = False, path: str = "/"):
    """
    Create an HTTP (and optional WebSocket) proxy to the given endpoint.
    Accepts positional apps, the `app=` kwarg, or both. Flattens any iterables
    and selects apps by type using gw.filter_apps.

    Returns a single app if one is provided, otherwise a tuple of apps.
    """
    # selectors for app types
    from bottle import Bottle

    def is_bottle_app(candidate) -> bool:
        return isinstance(candidate, Bottle)

    def is_fastapi_app(candidate) -> bool:
        return hasattr(candidate, "websocket")

    # collect apps by type
    bottle_apps = gw.filter_apps(*apps, kwarg=app, selector=is_bottle_app)
    fastapi_apps = gw.filter_apps(*apps, kwarg=app, selector=is_fastapi_app)

    prepared = []

    # if no matching apps, default to a new Bottle
    if not bottle_apps and not fastapi_apps:
        default = Bottle()
        prepared.append(_wire_proxy(default, endpoint, websockets, path))
    else:
        for b in bottle_apps:
            prepared.append(_wire_proxy(b, endpoint, websockets, path))
        for f in fastapi_apps:
            prepared.append(_wire_proxy(f, endpoint, websockets, path))

    return prepared[0] if len(prepared) == 1 else tuple(prepared)


def _wire_proxy(app, endpoint: str, websockets: bool, path: str):
    """
    Internal: attach HTTP and optional WS proxy routes
    to Bottle or FastAPI-compatible app.
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
