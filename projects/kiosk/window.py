"""Launch a minimal browser window on Windows using ``pywebview``."""

from __future__ import annotations

import sys
from typing import Optional

from gway import __, gw


def show(
    *,
    url: Optional[str] = None,
    host: str = __("[SITE_HOST]", "0.0.0.0"),
    port: int = __('[SITE_PORT]', '8888'),
    width: int = 1024,
    height: int = 768,
    fullscreen: bool = False,
) -> None:
    """Open ``url`` in a borderless window.

    Parameters
    ----------
    url:
        Full address to load. Defaults to ``http://{host}:{port}``.
    host, port:
        Used when ``url`` is not provided.
    width, height:
        Window size when ``fullscreen`` is ``False``.
    fullscreen:
        Launch the window in kiosk mode.
    """
    target = url or f"http://{host}:{port}"
    gw.verbose(f"[kiosk] Opening {target}")

    import webview

    webview.create_window(
        "App",
        url=target,
        width=width,
        height=height,
        frameless=True,
        resizable=False,
        fullscreen=fullscreen,
    )
    webview.start(gui="edgechromium" if sys.platform == "win32" else None)
