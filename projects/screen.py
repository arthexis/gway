import os
import platform
import subprocess
from datetime import datetime
from PIL import ImageGrab
from gway import gw


def _get_active_window():
    system = platform.system()

    if system == "Windows":
        try:
            import ctypes
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            length = user32.GetWindowTextLengthW(hwnd)
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buff, length + 1)
            return buff.value or "window"
        except Exception:
            return "window"

    elif system == "Darwin":
        try:
            script = 'tell application "System Events" to get name of first process whose frontmost is true'
            p = subprocess.Popen(
                ["osascript", "-e", script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            out, _ = p.communicate(timeout=2)
            name = out.decode("utf-8").strip()
            return name if name else "window"
        except Exception:
            return "window"

    else:
        try:
            p = subprocess.Popen(
                ["xdotool", "getactivewindow", "getwindowname"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            out, _ = p.communicate(timeout=2)
            name = out.decode("utf-8").strip()
            return name if name else "window"
        except Exception:
            return "window"


def _sanitize_filename(name: str) -> str:
    cleaned = "".join(
        c if (c.isalnum() or c in (" ", "_", "-")) else "_" for c in name
    )
    return cleaned.replace(" ", "_").strip("_") or "window"


def take_screenshot(mode: str = "full") -> str:
    """
    Take a screenshot in the specified mode and save it under:

        gw.resource("work", "screenshots")

    The filename will be:

        <active_window_name>_<YYYYMMDD_HHMMSS>.png

    Returns:
        The full path to the saved screenshot file.

    Modes:
        - "full": entire screen
        - "active"/"window": active window only (Windows only; falls back to full)
    """

    screenshots_dir = gw.resource("work", "screenshots")
    os.makedirs(screenshots_dir, exist_ok=True)

    window_name = _get_active_window()
    window_name = _sanitize_filename(window_name)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{window_name}_{timestamp}.png"
    filepath = os.path.join(screenshots_dir, filename)

    if mode in ("active", "window"):
        try:
            import pygetwindow as gwnd
            win = gwnd.getActiveWindow()
            if win and win.left != -32000:  # Avoid minimized windows
                bbox = (win.left, win.top, win.right, win.bottom)
                img = ImageGrab.grab(bbox=bbox)
            else:
                img = ImageGrab.grab()
        except Exception:
            img = ImageGrab.grab()
    else:
        img = ImageGrab.grab()

    img.save(filepath)

    return filepath


shot = take_screenshot
