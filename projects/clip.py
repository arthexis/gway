from gway import gw


def copy(value=None, *, notify=True):
    """Extracts the contents of the clipboard and returns it."""
    import pyperclip

    original = pyperclip.paste()
    if value is not None:
        gw.info(f"Clipboard accessed ->\n{original=}\n{value=}.")
        pyperclip.copy(value)
        distance = len(value) - len(original)
        if abs(distance) <= 40:
            gw.gui.notify(f"Clipboard modified: {value}")
        else:
            gw.gui.notify("Clipboard modified (%+d bytes)" % distance)
    else:
        gw.debug("clip.copy called with no value.")
    return original
