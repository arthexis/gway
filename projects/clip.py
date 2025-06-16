import time
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
        gw.warning(f"Clipboard accessed and content replaced (data not shown).")
        pyperclip.copy(value)
        distance = len(value) - len(original)
        if notify:
            if abs(distance) <= 40:
                gw.screen.notify(f"Clipboard modified: {value}")
            else:
                gw.screen.notify("Clipboard modified (%+d bytes)" % distance)
    else:
        gw.warning(f"Clipboard accessed in read-only mode (value witheld).")
        gw.debug("clip.copy called with no value.")

    return original


def track_history(interval: int = 5, *, stop_after=None, notify=True):
    """Tracks clipboard history by polling at regular intervals.

    Args:
        interval (int): Seconds to wait between checks. Default is 5 seconds.
        stop_after (int | None): Optional maximum duration (in seconds) before stopping.
        notify (bool): Whether to show GUI notifications for new entries.

    Writes:
        Appends new clipboard entries to 'work/clip/history.txt', separated by '\n...\n'.
    """
    import pyperclip
    import os

    history_path = gw.resource('work', 'clip', 'history.txt')
    os.makedirs(os.path.dirname(history_path), exist_ok=True)

    last_value = None
    start_time = time.time()

    gw.info(f"Started clipboard tracking every {interval}s.")
    try:
        while True:
            current = pyperclip.paste()
            clean_current = current.strip()

            if not clean_current or clean_current == last_value:
                time.sleep(interval)
                continue

            normalized = current.replace('\r\n', '\n').replace('\r', '\n').rstrip() + '\n'
            with open(history_path, 'a', encoding='utf-8') as f:
                if last_value is not None:
                    f.write("\n...\n")
                f.write(normalized)

            last_value = clean_current
            if notify:
                summary = clean_current if len(clean_current) <= 60 else clean_current[:57] + "..."
                gw.screen.notify("Clipboard captured: " + summary)
            gw.debug("New clipboard entry recorded.")

            if stop_after and (time.time() - start_time) > stop_after:
                gw.info("Clipboard tracking stopped after timeout.")
                break

            time.sleep(interval)
    except KeyboardInterrupt:
        gw.warning("Clipboard tracking manually interrupted.")


def view_history(*, selection: list = None, copy: bool = True, purge: bool = True):
    gw.verbose(f"Received {selection=}")
    selection = gw.to_list(selection) if selection else selection
    # TODO: If copy, concatenate selection, copy to clipboard
    # TODO: If purge, remove listed all items by sequence from history.txt
    raise NotImplementedError


def purge(*, history=False):
    """Clears clipboard and optionally wipes history file."""
    import pyperclip
    import os

    pyperclip.copy("")  # Clear clipboard
    gw.info("Clipboard contents purged.")

    if history:
        history_path = gw.resource('work', 'clip', 'history.txt')
        if os.path.exists(history_path):
            with open(history_path, 'w', encoding='utf-8') as f:
                f.write('')
            gw.info("Clipboard history purged.")
