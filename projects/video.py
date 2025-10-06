"""Video stream helpers for the standalone video project."""

from __future__ import annotations

from typing import Iterator, Iterable, Optional
from gway import gw


def capture(*, source: int = 0) -> Iterator:
    """Capture frames from a camera device.

    Parameters
    ----------
    source:
        Camera index passed to ``cv2.VideoCapture``. Defaults to ``0``.

    Returns
    -------
    Iterator
        Generator yielding frames as numpy arrays. The capture device is
        released automatically when iteration stops.
    """
    import cv2

    gw.debug(f"Opening camera source {source}")
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open camera {source}")

    def _generator() -> Iterator:
        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                yield frame
        finally:
            cap.release()
            gw.debug("Camera released")

    return _generator()


def display(stream: Iterable, *, screen: int = 0) -> bool:
    """Display frames from ``stream`` using pygame.

    Parameters
    ----------
    stream:
        An iterable yielding numpy array frames (H x W x 3, BGR).
    screen:
        Screen index (currently unused, placeholder for multi-screen setups).

    Returns
    -------
    bool
        ``True`` when the stream is consumed without errors.
    """
    if not hasattr(stream, "__iter__"):
        raise ValueError("stream must be an iterable of frames")

    import numpy as np  # noqa: F401 - only for type expectations
    import cv2
    import pygame

    iterator = iter(stream)
    try:
        first = next(iterator)
    except StopIteration:
        return True

    height, width = first.shape[:2]
    pygame.init()
    window = pygame.display.set_mode((width, height))

    def _show(frame):
        surf = pygame.surfarray.make_surface(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        window.blit(surf, (0, 0))
        pygame.display.flip()

    try:
        _show(first)
        for frame in iterator:
            _show(frame)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return True
        return True
    finally:
        pygame.quit()


def serve(
    stream: Optional[Iterable] = None,
    *,
    source: int = 0,
    host: str = "0.0.0.0",
    port: int = 8000,
    username: Optional[str] = None,
    password: Optional[str] = None,
    realm: str = "Camera",
) -> dict[str, object]:
    """Start an HTTP MJPEG stream server for ``stream``.

    Parameters
    ----------
    stream:
        Iterable yielding frames as numpy arrays. When ``None`` the function
        falls back to :func:`capture` using ``source``.
    source:
        Camera index forwarded to :func:`capture` when ``stream`` is ``None``.
    host, port:
        Network binding for the HTTP server. ``host`` defaults to ``0.0.0.0``
        so the service is reachable from the local network.
    username, password:
        Optional HTTP Basic Authentication credentials. If ``username`` is
        provided a ``WWW-Authenticate`` challenge is emitted until the correct
        credentials are supplied. ``password`` defaults to an empty string when
        omitted.
    realm:
        Auth realm shown in the login prompt.

    Returns
    -------
    dict
        Information about the server, including the URL and whether
        authentication is enabled.
    """

    import base64
    import contextlib
    import threading
    import time
    from http import HTTPStatus
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from socketserver import ThreadingMixIn

    import cv2

    iterator = iter(stream if stream is not None else capture(source=source))

    frame_lock = threading.Lock()
    latest_frame: Optional[bytes] = None
    stop_event = threading.Event()

    def _reader() -> None:
        nonlocal latest_frame
        try:
            for frame in iterator:
                ok, buffer = cv2.imencode(".jpg", frame)
                if not ok:
                    continue
                with frame_lock:
                    latest_frame = buffer.tobytes()
                if stop_event.is_set():
                    break
        finally:
            stop_event.set()

    reader_thread = threading.Thread(target=_reader, daemon=True)
    reader_thread.start()

    expected_auth: Optional[str]
    if username is None:
        expected_auth = None
    else:
        credential = f"{username}:{password or ''}"
        encoded = base64.b64encode(credential.encode("utf-8")).decode("ascii")
        expected_auth = f"Basic {encoded}"

    class _StreamingServer(ThreadingMixIn, HTTPServer):
        daemon_threads = True
        allow_reuse_address = True

    html_page = """<!DOCTYPE html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\">
    <title>Video stream</title>
    <style>
      body { font-family: sans-serif; text-align: center; background: #111; color: #eee; }
      img { max-width: 90vw; height: auto; border: 4px solid #444; border-radius: 8px; }
      main { margin-top: 2rem; }
    </style>
  </head>
  <body>
    <main>
      <h1>Live video</h1>
      <img src=\"/stream.mjpg\" alt=\"Live video stream\">
    </main>
  </body>
</html>
"""

    class StreamingHandler(BaseHTTPRequestHandler):
        server_version = "VideoServer/1.0"

        def _authorized(self) -> bool:
            if expected_auth is None:
                return True
            header = self.headers.get("Authorization")
            if header == expected_auth:
                return True
            self.send_response(HTTPStatus.UNAUTHORIZED)
            self.send_header("WWW-Authenticate", f'Basic realm="{realm}"')
            self.end_headers()
            return False

        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            if self.path in {"/", "/index.html"}:
                if not self._authorized():
                    return
                content = html_page.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return

            if self.path.startswith("/stream"):
                if not self._authorized():
                    return
                self.send_response(HTTPStatus.OK)
                self.send_header("Age", "0")
                self.send_header("Cache-Control", "no-cache, private")
                self.send_header("Pragma", "no-cache")
                self.send_header(
                    "Content-Type",
                    "multipart/x-mixed-replace; boundary=frame",
                )
                self.end_headers()
                while not stop_event.is_set():
                    with frame_lock:
                        frame = latest_frame
                    if frame is None:
                        time.sleep(0.05)
                        continue
                    try:
                        self.wfile.write(b"--frame\r\n")
                        self.wfile.write(b"Content-Type: image/jpeg\r\n\r\n")
                        self.wfile.write(frame)
                        self.wfile.write(b"\r\n")
                    except (BrokenPipeError, ConnectionResetError):
                        break
                return

            self.send_error(HTTPStatus.NOT_FOUND)

        def log_message(self, format: str, *args) -> None:  # noqa: A003 - signature defined by base class
            gw.debug("[video.serve] " + format % args)

    server = _StreamingServer((host, port), StreamingHandler)

    display_host = host if host not in {"0.0.0.0", "::"} else "localhost"
    url = f"http://{display_host}:{port}/"
    if expected_auth is None:
        gw.logger.info("Video stream available at %s", url)
    else:
        gw.logger.info(
            "Video stream available at %s (user: %s)",
            url,
            username,
        )

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        gw.logger.info("Shutting down video stream server")
    finally:
        stop_event.set()
        with contextlib.suppress(Exception):
            server.shutdown()
        server.server_close()
        reader_thread.join(timeout=1)

    return {"url": url, "auth": expected_auth is not None}
