"""RFID scanning utilities.

The helpers in this module rely on the default wiring expected by the
``mfrc522`` package's :class:`~mfrc522.SimpleMFRC522` reader. The pinout is
documented via :func:`pinout` so future integrations can double-check the
hardware connections without digging through the third-party library.

The :func:`scan` helper now performs pre-flight checks for the Linux SPI
device node that backs the MFRC522 driver. A missing ``/dev/spidev0.0`` is the
root cause behind the ``FileNotFoundError`` seen when SPI is disabled or wired
to a different chip select. Surfacing a helpful explanation makes the CLI
usable during bring-up on fresh Raspberry Pi OS images or on alternate
single-board computers where the kernel modules need to be enabled first.
"""

import sys
import time
import select
import glob
import os
from typing import Iterable


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

DEFAULT_SPI_DEVICE = "/dev/spidev0.0"
SPI_DEVICE_GLOB = "/dev/spidev*"


def _list_spi_devices() -> list[str]:
    """Return the available ``spidev`` device nodes in ``/dev``."""

    return sorted(glob.glob(SPI_DEVICE_GLOB))


def _format_device_list(devices: Iterable[str]) -> str:
    """Return a comma-separated list for displaying SPI candidates."""

    return ", ".join(sorted(devices))


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
    except ModuleNotFoundError as exc:  # pragma: no cover - hardware dependent
        missing = exc.name or str(exc)
        advice = []
        if missing == "mfrc522":
            advice.append(
                "Install the MFRC522 helper package with `pip install mfrc522`."
            )
        if missing in {"RPi", "RPi.GPIO"}:
            advice.append(
                "Install the Raspberry Pi GPIO bindings with `pip install RPi.GPIO` on a Pi."
            )
        if missing == "spidev":
            advice.append(
                "Install the SPI bindings with `sudo apt install python3-spidev` or `pip install spidev`."
            )
        if not advice:
            advice.append("Install the missing Python module and try again.")
        print(
            "RFID libraries not available: {missing}. {advice}".format(
                missing=missing,
                advice=" ".join(advice),
            )
        )
        return
    except RuntimeError as exc:  # pragma: no cover - hardware dependent
        print(
            "RFID libraries could not initialize: {exc}. "
            "Run on a Raspberry Pi or install GPIO bindings that expose the same API.".format(
                exc=exc
            )
        )
        return
    except Exception as exc:  # pragma: no cover - hardware dependent
        print(f"RFID libraries not available: {exc}")
        return

    if not os.path.exists(DEFAULT_SPI_DEVICE):
        candidates = [
            device for device in _list_spi_devices() if device != DEFAULT_SPI_DEVICE
        ]
        if candidates:
            print(
                "RFID SPI device {device} not found. Detected SPI interfaces: {candidates}. "
                "Move the reader to CE0 or extend the tool to target the desired bus/device.".format(
                    device=DEFAULT_SPI_DEVICE,
                    candidates=_format_device_list(candidates),
                )
            )
        else:
            print(
                "RFID SPI device {device} not found and no /dev/spidev* nodes are present. "
                "Enable SPI with `sudo raspi-config nonint do_spi 0`, confirm `dtparam=spi=on` in /boot/config.txt, "
                "and reboot so the kernel exposes the SPI device. On other boards load the appropriate SPI driver.".format(
                    device=DEFAULT_SPI_DEVICE
                )
            )
        return

    try:
        reader = SimpleMFRC522()
    except FileNotFoundError as exc:  # pragma: no cover - hardware dependent
        print(
            "RFID hardware interface not found: {exc}. "
            "Ensure the SPI device is available and enabled.".format(exc=exc)
        )
        return
    except PermissionError as exc:  # pragma: no cover - hardware dependent
        print(
            "RFID hardware interface permission denied: {exc}. "
            "Run the command with elevated privileges or add your user to the `spi` group.".format(
                exc=exc
            )
        )
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
