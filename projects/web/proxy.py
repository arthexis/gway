# projects/web/proxy.py

from fastapi import FastAPI
from gway import gw
import requests



def fallback_app(*,
        endpoint: str, app=None, websockets: bool = False, path: str = "/",
        mode: str = "extend", callback=None,
    ):
    """
    Create an HTTP (and optional WebSocket) fallback to the given endpoint.
    This assumes the remote endpoint replicates missing functionality or the
    entire service if it can't be provided locally.

    ``mode`` controls how the proxy is used:
    - ``replace``: replace all paths in the received app with the proxied endpoint.
    - ``extend``: redirect paths not configured locally to the proxy.
    - ``errors``: call the proxy only when the local handler raises an error or
      returns no data.
    - ``trigger``: use ``callback(request)`` to decide when to proxy.
    """
    # selectors for app types
    from bottle import Bottle



    # collect apps by type
    match app:
        case Bottle() as b:
            bottle_app, fastapi_app = b, None
        case FastAPI() as f:
            bottle_app, fastapi_app = None, f
        case list() | tuple() as seq:
            bottle_app = next((x for x in seq if isinstance(x, Bottle)), None)
            fastapi_app = next((x for x in seq if isinstance(x, FastAPI)), None)
        case None:
            bottle_app = fastapi_app = None
        case _ if isinstance(app, Bottle):
            bottle_app, fastapi_app = app, None
        case _ if isinstance(app, FastAPI):
            bottle_app, fastapi_app = None, app
        case _ if hasattr(app, "__iter__") and not isinstance(app, (str, bytes, bytearray)):
            bottle_app = next((x for x in app if isinstance(x, Bottle)), None)
            fastapi_app = next((x for x in app if isinstance(x, FastAPI)), None)
        case _:
            bottle_app = fastapi_app = None

    prepared = []

    # if no matching apps, default to a new Bottle
    if not bottle_app and not fastapi_app:
        default = Bottle()
        prepared.append(_wire_proxy(default, endpoint, websockets, path))
        if mode == "errors":
            _wire_error_fallback(default, endpoint, path)
    elif bottle_app:
        prepared.append(_wire_proxy(bottle_app, endpoint, websockets, path))
        if mode == "errors":
            _wire_error_fallback(bottle_app, endpoint, path)
    elif fastapi_app:
        prepared.append(_wire_proxy(fastapi_app, endpoint, websockets, path))
        if mode == "errors":
            _wire_error_fallback(fastapi_app, endpoint, path)


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

    raise RuntimeError("Unsupported app type for fallback_app: must be Bottle or FastAPI-compatible")


def _wire_error_fallback(app, endpoint: str, path: str):
    """Attach error-handling hooks/middleware that proxies failed calls."""
    is_fastapi = hasattr(app, "websocket")

    if is_fastapi:
        from fastapi import Request, Response
        import httpx

        @app.middleware("http")
        async def _proxy_on_error(request: Request, call_next):
            body = await request.body()
            try:
                resp = await call_next(request)
                if resp.status_code >= 500 or resp.status_code == 404 or not getattr(resp, "body", b""):
                    raise Exception("fallback to proxy")
                return resp
            except Exception:
                url = endpoint.rstrip("/") + request.url.path
                if request.url.query:
                    url += "?" + request.url.query
                async with httpx.AsyncClient() as client:
                    proxied = await client.request(request.method, url, headers=dict(request.headers), content=body)
                return Response(content=proxied.content, status_code=proxied.status_code, headers=proxied.headers)
        return app

    if hasattr(app, "route"):
        from bottle import request, response

        def _do_proxy():
            target = endpoint.rstrip("/") + request.fullpath
            headers = {k: v for k, v in request.headers.items()}
            try:
                resp = requests.request(request.method, target, headers=headers, data=request.body.read(), stream=True)
                response.status = resp.status_code
                for k, v in resp.headers.items():
                    response.set_header(k, v)
                return resp.content
            except Exception as e:
                gw.error("Proxy request failed: %s", e)
                response.status = 502
                return f"Proxy error: {e}"

        @app.error(404)
        @app.error(500)
        def _handle_errors(err):
            return _do_proxy()

        @app.hook("after_request")
        def _after_req():
            if not response.body:
                response.body = _do_proxy()

        return app

    raise RuntimeError("Unsupported app type for fallback_app: must be Bottle or FastAPI-compatible")
