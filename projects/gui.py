# projects/gui.py

import os
import platform
import subprocess
from datetime import datetime
from PIL import ImageGrab
from gway import gw


def notify(message, *, title="GWAY Notice", timeout=8):
    """Show a user interface notification with the specified title and message."""
    from plyer import notification

    try:
        notification.notify(
            title=title, message=message, app_name="gway", timeout=timeout)
        gw.info(f"Notification: {title} - {message}")
    except Exception as e:
        gw.critical(f"Error displaying: {str(e)}")
        raise


def lookup_font(*prefix):
    """Look up fonts installed on a Windows system by partial name (prefix).
    >> gsol font lookup Ari
    """
    import winreg
    font_prefix = " ".join(prefix)

    try:
        font_key_path = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, font_key_path) as font_key:
            num_values = winreg.QueryInfoKey(font_key)[1]
            matching_fonts = []

            prefix_lower = font_prefix.lower()
            for i in range(num_values):
                value_name, value_data, _ = winreg.EnumValue(font_key, i)
                name_only = value_name.split(" (")[0].strip()

                if prefix_lower in name_only.lower() or prefix_lower in value_data.lower():
                    matching_fonts.append(f"{name_only} -> {value_data}")

            return matching_fonts if matching_fonts else [f"No match for prefix: {font_prefix}"]

    except Exception as e:
        return [f"Error: {str(e)}"]


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


screenshot = take_screenshot
