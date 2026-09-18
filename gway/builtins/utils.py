import os
import random
import sys
from collections.abc import Sequence

from gway.sigils import Sigil

__all__ = [
    "sigils",
    "try_cast",
    "random_id",
    "notify",
    "redacted",
]

_EZ_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXY3456789"


def sigils(*args: str):
    """List valid sigils found in the given args."""
    text = "\n".join(args)
    return Sigil(text).list_sigils()


def try_cast(value, default=None, **types) -> tuple:
    """Try casting a value to each provided type."""
    for name, caster in types.items():
        try:
            new_value = caster(value)
            return name, new_value
        except Exception:
            continue
    return default, value


def random_id(length: int = 8, alphabet: str = _EZ_ALPHABET) -> str:
    """Generate a readable random ID."""
    return "".join(random.choices(alphabet, k=length))


def _can_use_gui(gateway) -> bool:
    """Return ``True`` when the GUI notification channel is available."""

    screen = getattr(gateway, "screen", None)
    if screen is None or not hasattr(screen, "notify"):
        studio = getattr(gateway, "studio", None)
        screen = getattr(studio, "screen", None)
        if screen is None or not hasattr(screen, "notify"):
            return False

    if sys.platform.startswith("linux"):
        for env_var in ("DISPLAY", "WAYLAND_DISPLAY", "SWAYSOCK"):
            if os.environ.get(env_var):
                return True
        return False

    return True


def _can_use_lcd(gateway) -> bool:
    """Return ``True`` when an LCD interface is available."""

    lcd = getattr(gateway, "lcd", None)
    return hasattr(lcd, "show")


def notify(
    message: str | None = None,
    *,
    title: str = "GWAY Notice",
    timeout: int = 10,
    lines: Sequence[str] | None = None,
):
    from gway import gw

    """Send a notification via GUI, LCD, email or console fallback."""

    if lines is not None:
        derived = "\n".join(str(part) for part in lines)
        body = message if message is not None else derived
    else:
        body = message

    if body is None:
        raise ValueError("notify requires a message or lines")

    if _can_use_gui(gw):
        screen = getattr(gw, "screen", None)
        if screen is None or not hasattr(screen, "notify"):
            studio = getattr(gw, "studio", None)
            screen = getattr(studio, "screen", None)
        notify_func = getattr(screen, "notify", None)
        try:
            notify_func(body, title=title, timeout=timeout)
            return "gui"
        except Exception as exc:
            gw.debug(f"GUI notify failed: {exc}")

    if _can_use_lcd(gw):
        try:
            hold_duration = timeout if timeout and timeout > 0 else 0
            lcd_text = body if not title else f"{title}\n{body}" if body else title
            gw.lcd.show(lcd_text, hold=hold_duration, wrap=True)
            return "lcd"
        except Exception as exc:
            gw.debug(f"LCD notify failed: {exc}")

    admin_email = os.environ.get("ADMIN_EMAIL")
    if hasattr(gw, "mail") and admin_email:
        try:  # pragma: no cover - depends on mail configuration
            gw.mail.send(title, body=body, to=admin_email)
            return "email"
        except Exception as exc:
            gw.debug(f"Email notify failed: {exc}")

    console_text = body if not title else f"{title}: {body}" if body else title
    print(console_text)
    gw.info(f"Console notify: {console_text}")
    return "console"


def redacted(text: str | None = None) -> str:
    """Replace sigils in ``text`` with ``"[REDACTED]"``.

    If ``text`` is empty or contains no sigils, return a single ``"[REDACTED]"``.
    """

    if text is None:
        return "[REDACTED]"

    value = str(text)
    redacted_value, count = Sigil._pattern.subn("[REDACTED]", value)
    if count == 0:
        return "[REDACTED]"
    return redacted_value
