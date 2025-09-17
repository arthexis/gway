"""RFID scanning utilities."""

import select
import sys
import time
from typing import Optional, Tuple, Type


def _load_rfid_dependencies() -> Optional[Tuple[Type[object], object]]:
    """Return the ``SimpleMFRC522`` class and ``RPi.GPIO`` module if available."""

    try:
        from mfrc522 import SimpleMFRC522  # type: ignore
    except ModuleNotFoundError as exc:  # pragma: no cover - hardware dependent
        print(
            "RFID support requires the 'mfrc522' package.\n"
            "Install it with: sudo pip install mfrc522"
        )
        print(f"Original error: {exc}")
        return None
    except Exception as exc:  # pragma: no cover - hardware dependent
        print(f"RFID libraries not available: {exc}")
        return None

    try:
        import RPi.GPIO as GPIO  # type: ignore
    except ModuleNotFoundError as exc:  # pragma: no cover - hardware dependent
        print(
            "RFID support requires the 'RPi.GPIO' package.\n"
            "Install it with: sudo apt-get install python3-rpi.gpio"
        )
        print(f"Original error: {exc}")
        return None
    except RuntimeError as exc:  # pragma: no cover - hardware dependent
        message = str(exc)
        if "sudo" in message.lower() or "root" in message.lower():
            print(
                "Access to GPIO requires elevated privileges.\n"
                "Rerun the command with: sudo gway rfid scan"
            )
        else:
            print(f"RFID libraries not available: {exc}")
        return None
    except Exception as exc:  # pragma: no cover - hardware dependent
        print(f"RFID libraries not available: {exc}")
        return None

    return SimpleMFRC522, GPIO


def scan():
    """Wait for a card and print its data until a key is pressed."""

    dependencies = _load_rfid_dependencies()
    if not dependencies:
        return

    SimpleMFRC522, GPIO = dependencies

    try:
        reader = SimpleMFRC522()
    except RuntimeError as exc:  # pragma: no cover - hardware dependent
        message = str(exc)
        if "sudo" in message.lower() or "root" in message.lower():
            print(
                "RFID reader access was denied.\n"
                "Rerun the command with elevated privileges: sudo gway rfid scan"
            )
        else:
            print(f"Unable to initialize RFID reader: {exc}")
        return
    except Exception as exc:  # pragma: no cover - hardware dependent
        print(f"Unable to initialize RFID reader: {exc}")
        return

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
