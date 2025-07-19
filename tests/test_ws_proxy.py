import unittest
import asyncio
import threading
import time
import socket
import sys

from gway.builtins import is_test_flag
from gway import gw

import websockets
from fastapi import FastAPI
import uvicorn


class _WSProxyHelper:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.thread = None
        self.stop_event = threading.Event()

    def start(self):
        async def echo(websocket):
            async for message in websocket:
                await websocket.send(message)

        async def run_server():
            async with websockets.serve(echo, self.host, self.port):
                while not self.stop_event.is_set():
                    await asyncio.sleep(0.1)

        def runner():
            asyncio.run(run_server())

        self.thread = threading.Thread(target=runner, daemon=True)
        self.thread.start()
        self._wait_for_port(self.port)

    def stop(self):
        if self.thread:
            self.stop_event.set()
            self.thread.join(timeout=5)
            self.thread = None

    @staticmethod
    def _wait_for_port(port, timeout=10):
        start = time.time()
        while time.time() - start < timeout:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=1):
                    return
            except OSError:
                time.sleep(0.1)
        raise TimeoutError(f"Port {port} not responding after {timeout} seconds")


class _ProxyServerHelper:
    def __init__(self, host, port, upstream):
        self.host = host
        self.port = port
        self.upstream = upstream
        self.thread = None
        self.server = None

    def start(self):
        app = FastAPI()
        gw.web.proxy.fallback_app(endpoint=self.upstream, app=app)
        config = uvicorn.Config(app, host=self.host, port=self.port, log_level="warning")
        self.server = uvicorn.Server(config)

        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.thread.start()
        self._wait_for_port(self.port)

    def stop(self):
        if self.server:
            self.server.should_exit = True
        if self.thread:
            self.thread.join(timeout=5)
            self.thread = None

    @staticmethod
    def _wait_for_port(port, timeout=10):
        start = time.time()
        while time.time() - start < timeout:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=1):
                    return
            except OSError:
                time.sleep(0.1)
        raise TimeoutError(f"Port {port} not responding after {timeout} seconds")


@unittest.skipUnless(is_test_flag("proxy"), "Proxy tests disabled")
class WebSocketProxyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.echo = _WSProxyHelper("127.0.0.1", 8765)
        cls.echo.start()
        cls.proxy = _ProxyServerHelper("127.0.0.1", 8766, "ws://127.0.0.1:8765")
        cls.proxy.start()

    @classmethod
    def tearDownClass(cls):
        cls.proxy.stop()
        cls.echo.stop()

    def test_websocket_echo_via_proxy(self):
        async def run_client():
            async with websockets.connect("ws://127.0.0.1:8766/echo") as ws:
                await ws.send("hello")
                return await ws.recv()
        result = asyncio.run(run_client())
        self.assertEqual(result, "hello")


if __name__ == "__main__":
    unittest.main()
