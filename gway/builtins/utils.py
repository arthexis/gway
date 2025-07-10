import random
import os
from gway.sigils import Sigil

__all__ = [
    "sigils",
    "try_cast",
    "random_id",
    "notify",
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


def notify(message: str, *, title: str = "GWAY Notice", timeout: int = 10):
    from gway import gw
    """Send a notification via GUI, email or console fallback."""
    try:
        gw.screen.notify(message, title=title, timeout=timeout)
        return "gui"
    except Exception as e:
        gw.debug(f"GUI notify failed: {e}")
    try:
        if hasattr(gw, "mail") and os.environ.get("ADMIN_EMAIL"):
            gw.mail.send(title, body=message, to=os.environ.get("ADMIN_EMAIL"))
            return "email"
    except Exception as e:  # pragma: no cover - mail may not be configured
        gw.debug(f"Email notify failed: {e}")
    print(message)
    gw.info(f"Console notify: {message}")
    return "console"
