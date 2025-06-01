# projects/screen.py

import os
import platform
import subprocess
from datetime import datetime
from PIL import ImageGrab
from gway import gw


def _get_active_window_name():
    """
    Return the title of the active/focused window. Falls back to "window"
    if anything goes wrong or if the platform isn’t recognized.
    """
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
        # AppleScript to get the frontmost process name
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
        # Assume Linux/X11: try `xdotool`
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
    """
    Replace characters that are not alphanumeric, space, underscore, or hyphen
    with underscores. Then collapse spaces into underscores.
    """
    # First replace any problematic char with "_"
    cleaned = "".join(
        c if (c.isalnum() or c in (" ", "_", "-")) else "_" for c in name
    )
    # Replace spaces with underscores, and strip any leading/trailing underscores
    return cleaned.replace(" ", "_").strip("_") or "window"


def take_screenshot() -> str:
    """
    Take a full‐screen screenshot and save it under:

        gw.resource("work", "screenshots")

    The filename will be:

        <active_window_name>_<YYYYMMDD_HHMMSS>.png

    Returns:
        The full path to the saved screenshot file.
    """

    # TODO: Implement a new mode param that defaults to "full"
    # with the current behavior, but allows for
    # "active" or "window" to only capture the active window instead of the full screen.

    

    # 1. Determine screenshots directory via GWAY’s resource helper
    screenshots_dir = gw.resource("work", "screenshots")
    os.makedirs(screenshots_dir, exist_ok=True)

    # 2. Get and sanitize the active‐window name
    window_name = _get_active_window_name()
    window_name = _sanitize_filename(window_name)

    # 3. Generate timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 4. Build filename and full path
    filename = f"{window_name}_{timestamp}.png"
    filepath = os.path.join(screenshots_dir, filename)

    # 5. Capture the screen and save as PNG
    img = ImageGrab.grab()
    img.save(filepath)

    return filepath


shot = take_screenshot
