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
import math
from typing import Iterable, Tuple, Optional


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


def _initialize_reader() -> Tuple[Optional[object], Optional[object]]:
    """Return an initialized ``SimpleMFRC522`` reader and GPIO module.

    The helper centralizes the import and hardware validation logic used by
    both :func:`scan` and :func:`write`. Returning ``(None, None)`` indicates
    that the reader could not be constructed and the caller should abort.
    """

    GPIO = None  # type: ignore[assignment]
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
        return None, None
    except RuntimeError as exc:  # pragma: no cover - hardware dependent
        print(
            "RFID libraries could not initialize: {exc}. "
            "Run on a Raspberry Pi or install GPIO bindings that expose the same API.".format(
                exc=exc
            )
        )
        return None, None
    except Exception as exc:  # pragma: no cover - hardware dependent
        print(f"RFID libraries not available: {exc}")
        return None, None

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
        return None, GPIO

    try:
        reader = SimpleMFRC522()
    except FileNotFoundError as exc:  # pragma: no cover - hardware dependent
        print(
            "RFID hardware interface not found: {exc}. "
            "Ensure the SPI device is available and enabled.".format(exc=exc)
        )
        return None, GPIO
    except PermissionError as exc:  # pragma: no cover - hardware dependent
        print(
            "RFID hardware interface permission denied: {exc}. "
            "Run the command with elevated privileges or add your user to the `spi` group.".format(
                exc=exc
            )
        )
        return None, GPIO

    return reader, GPIO


def pinout():
    """Return the expected wiring map between the RFID reader and the Pi.

    ``SimpleMFRC522`` defaults to ``spidev`` on ``/dev/spidev0.0`` (CE0) and
    pulls its reset pin high using ``GPIO.BOARD`` numbering, which maps to
    ``GPIO25`` on physical pin 22. The remaining connections align with the
    Raspberry Pi's SPI interface. Returning the mapping makes it easy to assert
    the wiring in tests or display it from the CLI.
    """

    return PINOUT.copy()


def _coerce_scan_threshold(value) -> int:
    """Normalize the ``after`` threshold into a positive integer."""

    if isinstance(value, bool):
        raise TypeError("after must be a positive integer")
    if isinstance(value, int):
        threshold = int(value)
    elif isinstance(value, float):
        if not value.is_integer():
            raise ValueError("after must be a positive integer")
        threshold = int(value)
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            raise ValueError("after must be a positive integer")
        try:
            threshold = int(stripped, 10)
        except ValueError as exc:  # pragma: no cover - validated below
            raise ValueError("after must be a positive integer") from exc
    else:
        raise TypeError("after must be a positive integer")

    if threshold < 1:
        raise ValueError("after must be a positive integer")
    return threshold


def _coerce_wait_seconds(value) -> float:
    """Normalize the ``wait`` timeout into a positive floating point value."""

    if isinstance(value, bool):
        raise TypeError("wait must be a positive number of seconds")
    if isinstance(value, (int, float)):
        seconds = float(value)
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            raise ValueError("wait must be a positive number of seconds")
        try:
            seconds = float(stripped)
        except ValueError as exc:  # pragma: no cover - validated below
            raise ValueError("wait must be a positive number of seconds") from exc
    else:
        raise TypeError("wait must be a positive number of seconds")

    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("wait must be a positive number of seconds")
    return seconds


def scan(*, after=None, once=False, wait=None):
    """Wait for a card and print its data until stopped or a threshold is met.

    Args:
        after: Optional positive integer specifying how many times the same
            card must be detected before the scan stops automatically.
        once: Convenience flag equivalent to ``after=1``.
        wait: Optional positive number of seconds after which the scan stops
            automatically.

    Returns:
        The UID of the card that satisfied the threshold when ``after`` or
        ``once`` is provided. Otherwise ``None`` when stopped manually or when
        initialization fails.

    The function attempts to use a ``SimpleMFRC522`` reader. If the required
    libraries are not available, an informative message is printed and the
    function exits.
    """
    threshold = None
    if after is not None:
        threshold = _coerce_scan_threshold(after)
    if once:
        once_threshold = 1
        if threshold is not None and threshold != once_threshold:
            raise ValueError("`once` cannot be combined with after != 1")
        threshold = once_threshold

    wait_seconds = None
    if wait is not None:
        wait_seconds = _coerce_wait_seconds(wait)

    reader, GPIO = _initialize_reader()
    if reader is None:
        return
    if wait_seconds is None:
        print("Scanning for RFID cards. Press any key to stop.")
    else:
        formatted_wait = f"{wait_seconds:g}"
        print(
            "Scanning for RFID cards. Press any key to stop. "
            "Automatically stopping after {seconds} seconds.".format(
                seconds=formatted_wait
            )
        )
    seen_counts: dict[object, int] = {}
    detected_uid = None
    try:
        deadline = None
        if wait_seconds is not None:
            deadline = time.monotonic() + wait_seconds
        while True:
            if deadline is not None and time.monotonic() >= deadline:
                break
            if select.select([sys.stdin], [], [], 0)[0]:
                break
            card_id, text = reader.read_no_block()
            if card_id is not None:
                text = text.strip() if isinstance(text, str) else text
                print(f"Card ID: {card_id} Text: {text}")
                if threshold is not None:
                    count = seen_counts.get(card_id, 0) + 1
                    seen_counts[card_id] = count
                    if count >= threshold:
                        detected_uid = card_id
                        break
            time.sleep(0.1)
    finally:  # pragma: no cover - hardware cleanup
        if GPIO is not None:
            try:
                GPIO.cleanup()  # type: ignore[attr-defined]
            except Exception:
                pass

    return detected_uid


def _coerce_uid(uid) -> int:
    """Normalize the provided UID into an integer."""

    if isinstance(uid, bool):
        raise TypeError("uid must be an integer, not a boolean")
    if isinstance(uid, (int,)):
        return int(uid)
    if isinstance(uid, float):
        if not uid.is_integer():
            raise ValueError("uid must be an integer value")
        return int(uid)
    if isinstance(uid, str):
        stripped = uid.strip()
        if not stripped:
            raise ValueError("uid must not be empty")
        try:
            return int(stripped, 10)
        except ValueError as exc:
            raise ValueError("uid must be a base-10 integer string") from exc
    raise TypeError("uid must be an integer or base-10 string")


def _coerce_auto_increment(value) -> int:
    """Return the increment to apply when auto-incrementing the UID."""

    if value is None:
        return 0
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, (int,)):
        return int(value)
    if isinstance(value, float):
        if not value.is_integer():
            raise ValueError("auto_increment must be an integer value")
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return 0
        lowered = stripped.lower()
        if lowered in {"false", "no", "off"}:
            return 0
        if lowered in {"true", "yes", "on"}:
            return 1
        try:
            return int(stripped, 10)
        except ValueError as exc:
            raise ValueError(
                "auto_increment must be a boolean or integer value"
            ) from exc
    raise TypeError("auto_increment must be a boolean, string, or integer value")


def write(*, uid, auto_increment=False, poll_interval=0.1):
    """Program an RFID card with a UID and report the written value.

    Args:
        uid: The base UID to write. When ``auto_increment`` is non-zero the
            provided UID is increased before being written to the card.
        auto_increment: When ``True`` increments the UID by ``1`` before
            writing. Providing an integer (or integer-like string) increments
            the UID by that value. ``False`` or ``0`` disables incrementing.
        poll_interval: Delay between polling attempts in seconds. Exposed for
            tests so they can advance immediately.

    Returns:
        A mapping describing the card that was programmed along with the
        written UID. When ``auto_increment`` is enabled the next UID in the
        sequence is returned under ``next_uid`` for convenience.
    """

    base_uid = _coerce_uid(uid)
    increment = _coerce_auto_increment(auto_increment)
    target_uid = base_uid + increment

    reader, GPIO = _initialize_reader()
    if reader is None:
        return None

    print(
        "Ready to write UID {uid}. Present an RFID card to the reader.".format(
            uid=target_uid
        )
    )

    card_id = None
    try:
        while True:
            card_id, _ = reader.read_no_block()
            if card_id is not None:
                reader.write(str(target_uid))
                print(f"Wrote UID {target_uid} to card {card_id}.")
                break
            time.sleep(poll_interval)
    finally:  # pragma: no cover - hardware cleanup
        if GPIO is not None:
            try:
                GPIO.cleanup()  # type: ignore[attr-defined]
            except Exception:
                pass

    result = {"card_id": card_id, "written_uid": target_uid}
    if increment:
        next_uid = target_uid + increment
        result["next_uid"] = next_uid
        print(f"Next UID: {next_uid}")
    return result
