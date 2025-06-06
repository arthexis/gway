# projects/clip.py

from gway import gw


def copy(value=None, *, notify=True, when=None):
    """Extracts or updates the clipboard contents.

    Args:
        value (str, optional): The value to copy to clipboard. If None, only reads the clipboard.
        notify (bool, optional): Whether to send a GUI notification. Default is True.
        when (str | Pattern, optional): If provided, must match clipboard contents. 
            Acts as a gatekeeper: if there's no match, returns None and skips updating.

    Returns:
        str | None: The previous clipboard content, or None if `when` did not match.
    """
    import pyperclip
    import re

    original = pyperclip.paste()

    if when:
        pattern = re.compile(when) if isinstance(when, str) else when
        if not pattern.search(original):
            gw.debug(f"Clipboard check skipped: no match for {when!r}.")
            return None

    if value is not None:
        gw.info(f"Clipboard accessed ->\n{original=}\n{value=}.")
        pyperclip.copy(value)
        distance = len(value) - len(original)
        if notify:
            if abs(distance) <= 40:
                gw.gui.notify(f"Clipboard modified: {value}")
            else:
                gw.gui.notify("Clipboard modified (%+d bytes)" % distance)
    else:
        gw.debug("clip.copy called with no value.")

    return original
