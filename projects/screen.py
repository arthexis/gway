# projects/gui.py

import platform
import subprocess
import re, glob, time, os
from datetime import datetime
import pygame
from PIL import Image, ImageGrab
from gway import gw


def notify(message, *, title="GWAY Notice", timeout=10):
    """
    Show a user interface notification with the specified title and message.
    Falls back to a visible console printout if GUI notification fails.
    """
    try:
        from plyer import notification
        notification.notify(
            title=title,
            message=message,
            app_name="gway",
            timeout=timeout
        )
        gw.info(f"Notification: {title} - {message}")
    except Exception as e:
        fallback = f"\n{'='*10} {title} {'='*10}\n{message}\n{'='*30}"
        print(fallback)
        gw.critical(f"Notification fallback: {fallback} (Error: {e})")


def lookup_font(*prefix):
    """Look up fonts installed on a Windows system by partial name (prefix).
    >> gway font lookup Ari
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


def shot(mode: str = "full") -> str:
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


def animate_gif(pattern, *, output_gif=None):
    resolved = gw.resource(pattern)
    if os.path.isdir(resolved):
        pngs = sorted(glob.glob(os.path.join(resolved, "*.png")))
        if not pngs:
            gw.abort(f"No .png files found in directory: {resolved}")
        sample_file = os.path.basename(pngs[0])
        base_dir = resolved
    else:
        sample_file = os.path.basename(resolved)
        base_dir = os.path.dirname(resolved) or "."

    # Detect [n] or “ - n” patterns (falls back to ctime sort)
    bracket = re.search(r'\[(\d+)\]', sample_file)
    dash    = re.search(r'^(.*?)([ \-_]+)(\d+)(\.png)$', sample_file)
    if bracket:
        pfx = sample_file.split(bracket.group(0))[0]
        sfx = sample_file.split(bracket.group(0))[1]
        rx  = re.compile(r'^' + re.escape(pfx) + r'\[(\d+)\]' + re.escape(sfx) + r'$')
        pat = f"{pfx}*{sfx}"
    elif dash:
        pfx = dash.group(1) + dash.group(2)
        sfx = dash.group(4)
        rx  = re.compile(r'^' + re.escape(pfx) + r'(\d+)' + re.escape(sfx) + r'$')
        pat = f"{pfx}*{sfx}"
    else:
        # No numbering → creation order
        fns = sorted(glob.glob(os.path.join(base_dir, "*.png")), key=os.path.getctime)
        if not fns:
            gw.abort(f"No .png files in {base_dir}")
        images = [Image.open(f).convert("RGBA") for f in fns]
        return _display_and_save(images, fns, _make_outpath(pattern, output_gif, base_dir))

    # Gather & sort numbered frames
    items = []
    for fn in glob.glob(os.path.join(base_dir, pat)):
        nm = os.path.basename(fn)
        m  = rx.match(nm)
        if m: items.append((int(m.group(1)), fn))
    if not items:
        gw.abort(f"No files matching pattern {pat!r}")
    items.sort(key=lambda x: x[0])
    fns = [fn for _, fn in items]
    images = [Image.open(fn).convert("RGBA") for fn in fns]

    return _display_and_save(images, fns, _make_outpath(pattern, output_gif, base_dir))


def _make_outpath(pattern, output_gif, base_dir):
    if output_gif:
        return output_gif
    base = os.path.basename(pattern.rstrip("/\\")) or "output"
    return os.path.join(base_dir, base + ".gif")


def _display_and_save(pil_images, frame_files, output_gif):
    # Helper: flatten transparent frames onto black
    def flatten_rgba(img):
        if img.mode != "RGBA":
            return img.convert("RGB")
        bg = Image.new("RGB", img.size, (0, 0, 0))
        bg.paste(img, mask=img.split()[3])
        return bg

    # 1) Show & time
    pygame.init()
    W, H = zip(*(im.size for im in pil_images))
    screen = pygame.display.set_mode((max(W), max(H)))
    pygame.display.set_caption("SPACE to advance")

    durations, last = [], None
    font = pygame.font.SysFont(None, 36)
    for i, img in enumerate(pil_images):
        surf = pygame.image.fromstring(img.tobytes(), img.size, img.mode)
        screen.fill((0,0,0)); screen.blit(surf,(0,0))
        screen.blit(font.render(f"Frame {i}",True,(255,255,255)),(10,10))
        pygame.display.flip()
        waiting = True
        while waiting:
            for e in pygame.event.get():
                if e.type==pygame.KEYDOWN and e.key==pygame.K_SPACE:
                    now = time.time()
                    if last is not None: durations.append(now-last)
                    last = now
                    waiting = False
                elif e.type==pygame.QUIT:
                    pygame.quit(); gw.abort("User closed window")
    pygame.quit()
    if len(durations)==len(pil_images)-1: durations.append(durations[-1])
    durations_ms = [int(d*1000) for d in durations]

    # 2) Flatten + global quantize
    flat = [flatten_rgba(im) for im in pil_images]
    master = flat[0].convert("P", palette=Image.ADAPTIVE, colors=256)
    pal   = [im.quantize(palette=master) for im in flat]

    # 3) Save full-frame, browser-compatible GIF
    pal[0].save(
        output_gif,
        save_all=True,
        append_images=pal[1:],
        duration=durations_ms,
        loop=0,
        disposal=1,
        optimize=True
    )
    print(f"Saved GIF → {output_gif}")

