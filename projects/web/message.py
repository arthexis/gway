# file: projects/web/message.py

"""Cookie-backed message banner utilities."""

import html
import re
from gway import gw


def write(text: str, *, sep: str = "\n", max_messages: int = 4, max_len: int = 180) -> None:
    """Store a short message in the ``message`` cookie if the project is enabled."""
    app = getattr(gw.web, "app", None)
    if not (app and getattr(app, "is_setup", lambda x: False)("web.message")):
        gw.warning("web.message not enabled; message discarded")
        return
    if not (app.is_setup("web.cookies") and gw.web.cookies.accepted()):
        gw.warning(f"Cannot store message without cookie consent: {text!r}")
        return

    if not isinstance(text, str):
        text = str(text)
    clean = re.sub(r"\s+", " ", text.strip())
    clean = re.sub(r"[<>]", "", clean)
    if len(clean) > max_len:
        clean = clean[:max_len]
    if not clean:
        return

    raw = gw.web.cookies.get("message", "") or ""
    msgs = [m for m in raw.split(sep) if m]
    msgs.append(clean)
    if len(msgs) > max_messages:
        msgs = msgs[-max_messages:]
    gw.web.cookies.set("message", sep.join(msgs))


def render(*, sep: str = "\n") -> str:
    """Return HTML for any stored messages, or an empty string."""
    app = getattr(gw.web, "app", None)
    if not (app and getattr(app, "is_setup", lambda x: False)("web.message")):
        return ""
    if not app.is_setup("web.cookies"):
        return ""
    try:
        raw_msg = gw.web.cookies.get("message", "")
    except Exception:
        raw_msg = ""
    if not raw_msg:
        return ""
    parts = [html.escape(m.strip()) for m in raw_msg.split(sep) if m.strip()]
    if not parts:
        return ""
    rows = "".join(f"<div>{p}</div>" for p in parts)
    return (
        "<div id='gw-message' style='background:#fffae6;color:#000;"
        "border:2px solid #d69e00;padding:0.7em 1.6em 0.7em 1em;"
        "margin-bottom:1em;position:relative;font-weight:bold;'>"
        + rows +
        "<a href='#' onclick=\"gwDismissMessage();return false;\" "
        "style='position:absolute;top:0.2em;right:0.6em;color:#900;"
        "text-decoration:none;font-size:1.2em;font-weight:bold;'>\u2715</a>"
        "</div>"
        "<script>function gwDismissMessage(){document.cookie='message=;path=/;"
        "expires=Thu, 01 Jan 1970 00:00:00 GMT';var m=document.getElementById('gw-message');"
        "if(m)m.style.display='none';}</script>"
    )
