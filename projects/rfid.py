"""RFID scanning utilities.

The helpers in this module rely on the default wiring expected by the
``mfrc522`` package's :class:`~mfrc522.SimpleMFRC522` reader. The pinout is
documented via :func:`pinout` so future integrations can double-check the
hardware connections without digging through the third-party library.
"""

import sys
import time
import select


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
