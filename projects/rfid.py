"""RFID scanning utilities."""

import sys
import time
import select


def scan():
    """Wait for a card and print its data until a key is pressed.

    The function attempts to use a ``SimpleMFRC522`` reader. If the required
    libraries are not available, an informative message is printed and the
    function exits.
    """
    try:
        from mfrc522 import SimpleMFRC522  # type: ignore
        import RPi.GPIO as GPIO  # type: ignore
    except Exception as exc:  # pragma: no cover - hardware dependent
        print(f"RFID libraries not available: {exc}")
        return

    reader = SimpleMFRC522()
    print("Scanning for RFID cards. Press any key to stop.")
    try:
        while True:
            if select.select([sys.stdin], [], [], 0)[0]:
                break
            card_id, text = reader.read_no_block()
            if card_id:
                text = text.strip() if isinstance(text, str) else text
                print(f"Card ID: {card_id} Text: {text}")
            time.sleep(0.1)
    finally:  # pragma: no cover - hardware cleanup
        try:
            GPIO.cleanup()  # type: ignore
        except Exception:
            pass
