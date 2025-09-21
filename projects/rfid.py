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
import csv as csv_module
import datetime as dt
from dataclasses import dataclass
from typing import Iterable, Tuple, Optional, Sequence


from gway import gw


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

DEFAULT_KEY_BYTES: Tuple[int, ...] = (0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF)
COMMON_MIFARE_CLASSIC_KEYS: Tuple[Tuple[int, ...], ...] = (
    DEFAULT_KEY_BYTES,
    (0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5),
    (0xB0, 0xB1, 0xB2, 0xB3, 0xB4, 0xB5),
    (0x4D, 0x3A, 0x99, 0xC3, 0x51, 0xDD),
    (0x1A, 0x2B, 0x3C, 0x4D, 0x5E, 0x6F),
    (0x00, 0x00, 0x00, 0x00, 0x00, 0x00),
    (0xD3, 0xF7, 0xD3, 0xF7, 0xD3, 0xF7),
)


DEFAULT_CSV_FILENAME = "rfid-scan.csv"


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


@dataclass
class BlockReadResult:
    """Result of attempting to read a single RFID block."""

    block: int
    data: Optional[Tuple[int, ...]] = None
    key_type: Optional[str] = None
    key_hex: Optional[str] = None
    guessed: bool = False
    guess_attempted: bool = False
    error: Optional[str] = None


def _poll_for_card(reader) -> Optional[Tuple[int, Sequence[int], str]]:
    """Return the card ID, UID bytes, and stored text for a detected card."""

    try:
        chip = reader.READER  # type: ignore[attr-defined]
    except AttributeError:
        return None

    request = getattr(chip, "MFRC522_Request", None)
    anticoll = getattr(chip, "MFRC522_Anticoll", None)
    select_tag = getattr(chip, "MFRC522_SelectTag", None)
    stop_crypto = getattr(chip, "MFRC522_StopCrypto1", None)
    auth = getattr(chip, "MFRC522_Auth", None)
    read_block = getattr(chip, "MFRC522_Read", None)

    if not all([request, anticoll, select_tag, stop_crypto, auth, read_block]):
        return None

    try:
        status, _ = request(chip.PICC_REQIDL)
    except Exception:  # pragma: no cover - hardware dependent
        return None
    if status != getattr(chip, "MI_OK", 0):
        return None

    status, uid = anticoll()
    if status != getattr(chip, "MI_OK", 0) or not uid:
        return None

    try:
        card_id = reader.uid_to_num(uid)
    except Exception:
        return None

    text = ""
    try:
        select_tag(uid)
        key_bytes = getattr(reader, "KEY", list(DEFAULT_KEY_BYTES))
        status = auth(chip.PICC_AUTHENT1A, 11, list(key_bytes), uid)
        if status == getattr(chip, "MI_OK", 0):
            data: list[int] = []
            for block in getattr(reader, "BLOCK_ADDRS", []):
                block_data = read_block(block)
                if block_data:
                    data.extend(int(value) & 0xFF for value in block_data)
            if data:
                try:
                    text = "".join(chr(value) for value in data)
                except Exception:
                    text = ""
    finally:
        try:
            stop_crypto()
        except Exception:
            pass

    return card_id, tuple(int(part) & 0xFF for part in uid), text


def _coerce_block(value) -> int:
    """Return the block number requested by the user."""

    if isinstance(value, bool):
        raise TypeError("block must be an integer between 0 and 255")
    if isinstance(value, (int,)):
        block = int(value)
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            raise ValueError("block must be an integer between 0 and 255")
        base = 10
        if stripped.lower().startswith("0x"):
            stripped = stripped[2:]
            base = 16
        try:
            block = int(stripped, base)
        except ValueError as exc:  # pragma: no cover - validated in tests
            raise ValueError("block must be an integer between 0 and 255") from exc
    else:
        raise TypeError("block must be an integer between 0 and 255")

    if block < 0 or block > 255:
        raise ValueError("block must be an integer between 0 and 255")
    return block


def _parse_key_bytes(value, *, parameter: str) -> Tuple[int, ...]:
    """Normalize CLI key arguments into tuples of bytes."""

    if isinstance(value, bool):
        raise TypeError(f"{parameter} must be a 6-byte hex key")
    if isinstance(value, (bytes, bytearray)):
        data = tuple(int(part) & 0xFF for part in value)
    elif isinstance(value, int):
        hex_text = f"{value:012X}"
        data = tuple(int(hex_text[i : i + 2], 16) for i in range(0, 12, 2))
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            raise ValueError(f"{parameter} must be a 6-byte hex key")
        cleaned = stripped.replace(" ", "").replace(":", "").replace("-", "")
        if cleaned.lower().startswith("0x"):
            cleaned = cleaned[2:]
        if len(cleaned) != 12:
            raise ValueError(f"{parameter} must be a 12-digit hex string")
        try:
            data = tuple(int(cleaned[i : i + 2], 16) for i in range(0, 12, 2))
        except ValueError as exc:  # pragma: no cover - validated in tests
            raise ValueError(f"{parameter} must be a 12-digit hex string") from exc
    else:
        try:
            data = tuple(int(part) & 0xFF for part in value)
        except Exception as exc:
            raise TypeError(f"{parameter} must be a 6-byte hex key") from exc

    if len(data) != 6:
        raise ValueError(f"{parameter} must contain exactly 6 bytes")
    for byte in data:
        if byte < 0 or byte > 0xFF:
            raise ValueError(f"{parameter} values must be between 0x00 and 0xFF")
    return data


def _prepare_key_candidates(
    key_a, key_b, *, guess_defaults: bool
) -> Tuple[dict[str, list[Tuple[Tuple[int, ...], bool]]], bool]:
    """Return the keys to try for each key type along with guess usage."""

    candidates: dict[str, list[Tuple[Tuple[int, ...], bool]]] = {"A": [], "B": []}
    if key_a is not None:
        candidates["A"].append((_parse_key_bytes(key_a, parameter="key_a"), False))
    if key_b is not None:
        candidates["B"].append((_parse_key_bytes(key_b, parameter="key_b"), False))

    guess_mode = False
    if not candidates["A"] and not candidates["B"]:
        if guess_defaults:
            guess_mode = True
            for key in COMMON_MIFARE_CLASSIC_KEYS:
                candidates["A"].append((key, True))
                candidates["B"].append((key, True))
        else:
            candidates["A"].append((DEFAULT_KEY_BYTES, False))

    return candidates, guess_mode


def _determine_blocks(block: Optional[int], *, deep: bool) -> list[int]:
    """Return the list of blocks to read based on user input."""

    if block is not None:
        return [block]
    if deep:
        return list(range(64))
    return [0, 1, 2, 3]


def _read_blocks(
    reader,
    uid: Sequence[int],
    blocks: Sequence[int],
    key_candidates: dict[str, list[Tuple[Tuple[int, ...], bool]]],
    *,
    guess_mode: bool,
) -> list[BlockReadResult]:
    """Attempt to read each requested block using the provided keys."""

    results: list[BlockReadResult] = []
    if not blocks:
        return results

    try:
        chip = reader.READER  # type: ignore[attr-defined]
    except AttributeError:
        return results

    select_tag = getattr(chip, "MFRC522_SelectTag", None)
    auth = getattr(chip, "MFRC522_Auth", None)
    read_block = getattr(chip, "MFRC522_Read", None)
    stop_crypto = getattr(chip, "MFRC522_StopCrypto1", None)
    if not all([select_tag, auth, read_block, stop_crypto]):
        return results

    mi_ok = getattr(chip, "MI_OK", 0)
    auth_codes = {
        "A": getattr(chip, "PICC_AUTHENT1A", None),
        "B": getattr(chip, "PICC_AUTHENT1B", None),
    }

    unique_blocks = sorted(dict.fromkeys(int(block) for block in blocks))
    for block in unique_blocks:
        result = BlockReadResult(block=block)
        result.guess_attempted = guess_mode or any(
            guessed for key_list in key_candidates.values() for _, guessed in key_list
        )
        try:
            select_tag(uid)
        except Exception:
            result.error = "failed to select tag"
            results.append(result)
            continue

        auth_block = (block // 4) * 4 + 3
        success = False
        try:
            for key_type in ("A", "B"):
                auth_code = auth_codes.get(key_type)
                if auth_code is None:
                    continue
                for key_bytes, guessed in key_candidates.get(key_type, []):
                    try:
                        status = auth(auth_code, auth_block, list(key_bytes), uid)
                    except Exception:
                        status = None
                    if status == mi_ok:
                        try:
                            block_data = read_block(block)
                        except Exception:
                            block_data = None
                        if block_data is None:
                            data_tuple: Tuple[int, ...] = tuple()
                        else:
                            data_tuple = tuple(int(value) & 0xFF for value in block_data)
                        result.data = data_tuple
                        result.key_type = key_type
                        result.key_hex = "".join(f"{byte:02X}" for byte in key_bytes)
                        result.guessed = guessed
                        success = True
                        break
                if success:
                    break
        finally:
            try:
                stop_crypto()
            except Exception:
                pass

        if not success:
            if result.guess_attempted:
                result.error = "authentication failed using provided and default keys"
            else:
                result.error = "authentication failed with provided keys"
        results.append(result)

    return results


def _format_block_result(result: BlockReadResult) -> str:
    """Render a :class:`BlockReadResult` for console output."""

    prefix = f"Block {result.block:02d}"
    if result.error:
        return f"{prefix}: {result.error}."

    key_info = ""
    if result.key_type and result.key_hex:
        key_info = f" (Key {result.key_type} {result.key_hex}"
        if result.guessed:
            key_info += " guessed"
        key_info += ")"

    if not result.data:
        return f"{prefix}{key_info}: <no data>"

    hex_bytes = " ".join(f"{byte:02X}" for byte in result.data)
    ascii_text = "".join(chr(byte) if 32 <= byte < 127 else "." for byte in result.data)
    return f"{prefix}{key_info}: {hex_bytes}  |{ascii_text}|"


def _normalize_csv_parts(csv_option) -> Optional[tuple[object, ...]]:
    """Normalize the ``csv`` argument into resource path components."""

    if csv_option is None or csv_option is False:
        return None
    if isinstance(csv_option, bool):
        return ("rfid", DEFAULT_CSV_FILENAME)
    if isinstance(csv_option, os.PathLike):
        return (csv_option,)
    if isinstance(csv_option, str):
        target = csv_option.strip()
        if not target:
            return ("rfid", DEFAULT_CSV_FILENAME)
        return (target,)
    raise TypeError("csv must be a boolean flag or a path-like value")


def _open_csv_writer(path):
    """Return an append-mode CSV file handle and writer for ``path``."""

    needs_header = True
    if path.exists():
        try:
            needs_header = path.stat().st_size == 0
        except OSError:
            needs_header = True

    csv_file = path.open("a", newline="", encoding="utf-8")
    writer = csv_module.writer(csv_file)
    if needs_header:
        writer.writerow(["timestamp", "card_id", "text"])
        csv_file.flush()
    return csv_file, writer


def scan(
    *,
    after=None,
    once=False,
    wait=None,
    block=None,
    deep=False,
    key_a=None,
    key_b=None,
    csv=None,
):
    """Wait for a card and print its data until stopped or a threshold is met.

    Args:
        after: Optional positive integer specifying how many times the same
            card must be detected before the scan stops automatically.
        once: Convenience flag equivalent to ``after=1``.
        wait: Optional positive number of seconds after which the scan stops
            automatically.
        block: Optional block number to read from the presented card.
        deep: When ``True`` read all 64 blocks of a MIFARE Classic card.
        key_a: Hex-encoded key to authenticate as key A when reading blocks.
        key_b: Hex-encoded key to authenticate as key B when reading blocks.
        csv: When provided, log detected cards to a CSV file. Pass ``True`` to
            use the default ``work/rfid/`` location defined by
            :data:`DEFAULT_CSV_FILENAME` or supply a custom file name.

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

    block_number = None
    if block is not None:
        block_number = _coerce_block(block)

    blocks_to_read = _determine_blocks(block_number, deep=deep)
    should_guess_defaults = bool(
        (block_number is not None or deep) and key_a is None and key_b is None
    )
    key_candidates, guess_mode = _prepare_key_candidates(
        key_a, key_b, guess_defaults=should_guess_defaults
    )

    csv_parts = _normalize_csv_parts(csv)

    reader, GPIO = _initialize_reader()
    if reader is None:
        return

    csv_file = None
    csv_writer = None
    detected_uid = None
    try:
        if csv_parts is not None:
            csv_path = gw.resource("work", *csv_parts)
            csv_file, csv_writer = _open_csv_writer(csv_path)
            print(f"Logging scans to {csv_path}")

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
        deadline = None
        if wait_seconds is not None:
            deadline = time.monotonic() + wait_seconds
        while True:
            if deadline is not None and time.monotonic() >= deadline:
                break
            if select.select([sys.stdin], [], [], 0)[0]:
                break

            card_info = _poll_for_card(reader)
            if card_info is None:
                time.sleep(0.1)
                continue

            card_id, uid_bytes, card_text = card_info
            display_text = card_text.strip() if isinstance(card_text, str) else card_text
            print(f"Card ID: {card_id} Text: {display_text}")

            if csv_writer is not None and csv_file is not None:
                timestamp = dt.datetime.now().isoformat()
                csv_writer.writerow([timestamp, card_id, display_text])
                csv_file.flush()

            block_results = _read_blocks(
                reader, uid_bytes, blocks_to_read, key_candidates, guess_mode=guess_mode
            )
            for result in block_results:
                print(_format_block_result(result))

            if threshold is not None:
                count = seen_counts.get(card_id, 0) + 1
                seen_counts[card_id] = count
                if count >= threshold:
                    detected_uid = card_id
                    break

            time.sleep(0.1)
    finally:  # pragma: no cover - hardware cleanup
        if csv_file is not None:
            try:
                csv_file.close()
            except Exception:
                pass
        if GPIO is not None:
            try:
                GPIO.cleanup()  # type: ignore[attr-defined]
            except Exception:
                pass

    return detected_uid


def _coerce_non_negative_seconds(value, *, allow_zero: bool = False, name: str = "value") -> float:
    """Return a non-negative float extracted from *value*."""

    if value is None:
        return 0.0
    if isinstance(value, bool):
        raise TypeError(f"{name} must be a non-negative number")
    if isinstance(value, (int, float)):
        seconds = float(value)
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            raise ValueError(f"{name} must be a non-negative number")
        try:
            seconds = float(stripped)
        except ValueError as exc:
            raise ValueError(f"{name} must be a non-negative number") from exc
    else:
        raise TypeError(f"{name} must be a non-negative number")

    if not math.isfinite(seconds) or seconds < 0 or (seconds == 0 and not allow_zero):
        raise ValueError(f"{name} must be {'non-negative' if allow_zero else 'positive'}")
    return seconds


def start_trigger(
    *,
    trigger: str = "rfid_trigger",
    section: str | None = None,
    after=None,
    debounce=1.0,
    poll_interval=0.1,
):
    """Monitor the RFID reader and run *trigger* for each detected card.

    Args:
        trigger: Recipe name or path to execute when a card satisfies the
            detection threshold.
        section: Optional recipe ``#`` section name to execute when triggering.
        after: Optional number of detections required before firing. Defaults to
            ``1`` (trigger immediately on the first read).
        debounce: Minimum number of seconds before the same card can trigger
            the recipe again. ``0`` disables debouncing.
        poll_interval: Delay between polling attempts while waiting for cards.

    The function blocks until interrupted (e.g. ``Ctrl+C``) so it can be run as
    a background service. Each time a card triggers the recipe the UID is
    exposed as ``[RFID_UID]`` within the recipe context.
    """

    threshold = _coerce_scan_threshold(after) if after is not None else 1
    debounce_seconds = _coerce_non_negative_seconds(debounce, allow_zero=True, name="debounce")
    poll_seconds = _coerce_wait_seconds(poll_interval)

    reader, GPIO = _initialize_reader()
    if reader is None:
        return None

    section_note = f" section '{section}'" if section else ""
    print(
        "RFID trigger armed. Present a card to run '{trigger}'{suffix}.".format(
            trigger=trigger,
            suffix=section_note,
        )
    )

    seen_counts: dict[int, int] = {}
    last_triggered: dict[int, float] = {}

    try:
        while True:
            card_info = _poll_for_card(reader)
            if card_info is None:
                time.sleep(poll_seconds)
                continue

            card_id, uid_bytes, card_text = card_info
            count = seen_counts.get(card_id, 0) + 1
            seen_counts[card_id] = count
            if count < threshold:
                time.sleep(poll_seconds)
                continue

            seen_counts.pop(card_id, None)
            now = time.monotonic()
            last_time = last_triggered.get(card_id)
            if last_time is not None and now - last_time < debounce_seconds:
                time.sleep(poll_seconds)
                continue

            last_triggered[card_id] = now
            print(f"Triggering recipe '{trigger}' for UID {card_id}")
            try:
                gw.run_recipe(trigger, section=section, RFID_UID=str(card_id))
            except KeyboardInterrupt:
                raise
            except Exception as exc:  # pragma: no cover - defensive logging
                print(f"Recipe '{trigger}' failed: {exc}")

            time.sleep(poll_seconds)
    except KeyboardInterrupt:
        print("RFID trigger stopped.")
    finally:  # pragma: no cover - hardware cleanup
        if GPIO is not None:
            try:
                GPIO.cleanup()  # type: ignore[attr-defined]
            except Exception:
                pass

    return None


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
