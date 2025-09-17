"""RFID scanning utilities.

The helpers in this module rely on the default wiring expected by the
``mfrc522`` package's :class:`~mfrc522.SimpleMFRC522` reader. The pinout is
documented via :func:`pinout` so future integrations can double-check the
hardware connections without digging through the third-party library.
"""

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


PINOUT = {
    "SDA": "CE0 (GPIO8, physical pin 24)",
    "SCK": "SCLK (GPIO11, physical pin 23)",
    "MOSI": "MOSI (GPIO10, physical pin 19)",
    "MISO": "MISO (GPIO9, physical pin 21)",
    "IRQ": "GPIO4 (physical pin 7)",
    "GND": "GND (physical pin 6)",
    "RST": "GPIO25 (physical pin 22)",
    "3v3": "3V3 (physical pin 1)",
}


def pinout():
    """Return the expected wiring map between the RFID reader and the Pi.

    ``SimpleMFRC522`` defaults to ``spidev`` on ``/dev/spidev0.0`` (CE0) and
    pulls its reset pin high using ``GPIO.BOARD`` numbering, which maps to
    ``GPIO25`` on physical pin 22. The remaining connections align with the
    Raspberry Pi's SPI interface. Returning the mapping makes it easy to assert
    the wiring in tests or display it from the CLI.
    """

    return PINOUT.copy()


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
