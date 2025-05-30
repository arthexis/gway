from gway import requires, gw


@requires("requests", "httpx", "websockets", "fastapi")
def setup_app(*, endpoint: str, app=None, websockets: bool = False, path="/"):
    """
    Create an HTTP proxy to the given endpoint.
    If websockets=True and app is FastAPI or None, add WebSocket proxy support.
    If app is None and websockets=True, creates a new FastAPI app.
    If app is Bottle, only HTTP proxy supported.
    """
    import requests

    # Detect FastAPI
    is_fastapi = False
    if app is not None:
        is_fastapi = hasattr(app, "websocket")

    # Auto enable websockets if FastAPI app detected and websockets not explicitly set True
    if is_fastapi and not websockets:
        websockets = True

    # If app is None and websockets is True, create FastAPI app
    if app is None and websockets:
        from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
        import httpx
        import websockets
        import asyncio

        app = FastAPI()
        base_path = path.rstrip("/")
        if base_path == "":
            base_path = "/"

        @app.api_route(base_path + "/{full_path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
        async def proxy_http(request: Request, full_path: str):
            url = endpoint.rstrip("/") + "/" + full_path
            client = httpx.AsyncClient()
            headers = dict(request.headers)
            body = await request.body()
            resp = await client.request(request.method, url, headers=headers, content=body)
            return resp.content, resp.status_code, resp.headers.items()

        if websockets:
            @app.websocket(base_path + "/{full_path:path}")
            async def proxy_ws(websocket: WebSocket, full_path: str):
                upstream_ws_url = endpoint.rstrip("/") + "/" + full_path
                await websocket.accept()

                try:
                    async with websockets.connect(upstream_ws_url) as upstream_ws:

                        async def client_to_upstream():
                            while True:
                                msg = await websocket.receive_text()
                                await upstream_ws.send(msg)

                        async def upstream_to_client():
                            while True:
                                msg = await upstream_ws.recv()
                                await websocket.send_text(msg)

                        await asyncio.gather(client_to_upstream(), upstream_to_client())

                except WebSocketDisconnect:
                    pass
                except Exception as e:
                    gw.error(f"WebSocket proxy error: {e}")

        return app

    # If app is Bottle, setup HTTP proxy only
    if hasattr(app, "route"):
        from bottle import request
        @app.route(path + "<path:path>", method=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
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

        if websockets:
            gw.warning("WebSocket proxy requested but Bottle does not support WebSockets; ignoring websockets=True")

        return app

    # Otherwise, assume FastAPI-like app and append HTTP + WS proxy if requested
    if is_fastapi:
        from fastapi import WebSocket, WebSocketDisconnect, Request
        import httpx
        import websockets
        import asyncio

        base_path = path.rstrip("/")
        if base_path == "":
            base_path = "/"

        @app.api_route(base_path + "/{full_path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
        async def proxy_http(request: Request, full_path: str):
            url = endpoint.rstrip("/") + "/" + full_path
            client = httpx.AsyncClient()
            headers = dict(request.headers)
            body = await request.body()
            resp = await client.request(request.method, url, headers=headers, content=body)
            return resp.content, resp.status_code, resp.headers.items()

        if websockets:
            @app.websocket(base_path + "/{full_path:path}")
            async def proxy_ws(websocket: WebSocket, full_path: str):
                upstream_ws_url = endpoint.rstrip("/") + "/" + full_path
                await websocket.accept()

                try:
                    async with websockets.connect(upstream_ws_url) as upstream_ws:

                        async def client_to_upstream():
                            while True:
                                msg = await websocket.receive_text()
                                await upstream_ws.send(msg)

                        async def upstream_to_client():
                            while True:
                                msg = await upstream_ws.recv()
                                await websocket.send_text(msg)

                        await asyncio.gather(client_to_upstream(), upstream_to_client())

                except WebSocketDisconnect:
                    pass
                except Exception as e:
                    gw.error(f"WebSocket proxy error: {e}")

        return app

    # Unsupported app type
    raise RuntimeError("Unsupported app type for setup_proxy: must be Bottle or FastAPI-compatible")

