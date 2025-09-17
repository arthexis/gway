# file: projects/lcd.py
"""I²C LCD helpers.

Display messages on a 16×2 character LCD connected via an I²C backpack
(PCF8574 based).  The Raspberry Pi must have the I²C interface enabled
and the `python3-smbus` package installed.

Setup steps::

    sudo raspi-config      # Interface Options → I2C → Enable
    sudo apt-get update
    sudo apt-get install -y i2c-tools python3-smbus
    sudo adduser pi i2c    # optional, allows running without sudo
    sudo reboot

Wiring (typical backpack):
* VCC → 5V
* GND → GND
* SDA → GPIO2 (SDA1)
* SCL → GPIO3 (SCL1)
"""

from __future__ import annotations

import datetime
import time
import types
from gway import gw

# LCD constants
LCD_WIDTH = 16
LCD_CHR = 1
LCD_CMD = 0
LCD_LINE_1 = 0x80
LCD_LINE_2 = 0xC0
LCD_BACKLIGHT = 0x08
ENABLE = 0b00000100
E_PULSE = 0.0005
E_DELAY = 0.0005


_backlight_mask = LCD_BACKLIGHT


def _lcd_toggle_enable(bus, addr: int, data: int) -> None:
    """Toggle enable bit to latch data."""
    time.sleep(E_DELAY)
    bus.write_byte(addr, data | ENABLE)
    time.sleep(E_PULSE)
    bus.write_byte(addr, data & ~ENABLE)
    time.sleep(E_DELAY)


def _lcd_byte(bus, addr: int, value: int, mode: int) -> None:
    """Send a single command or character byte."""
    high = mode | (value & 0xF0) | _backlight_mask
    low = mode | ((value << 4) & 0xF0) | _backlight_mask
    for nibble in (high, low):
        bus.write_byte(addr, nibble)
        _lcd_toggle_enable(bus, addr, nibble)


def _lcd_init(bus, addr: int) -> None:
    """Initialise display in 4‑bit mode."""
    for cmd in (0x33, 0x32, 0x06, 0x0C, 0x28, 0x01):
        _lcd_byte(bus, addr, cmd, LCD_CMD)
    time.sleep(E_DELAY)


def _lcd_string(bus, addr: int, message: str, line: int) -> None:
    """Write a string to one line of the display."""
    message = message.ljust(LCD_WIDTH)[:LCD_WIDTH]
    _lcd_byte(bus, addr, line, LCD_CMD)
    for ch in message:
        _lcd_byte(bus, addr, ord(ch), LCD_CHR)


def _coerce_timezone(tz: str | datetime.tzinfo | None) -> datetime.tzinfo | None:
    """Return a ``tzinfo`` instance for *tz*.

    Strings are resolved using :class:`zoneinfo.ZoneInfo` when available with a
    special-case for ``"UTC"``/``"Z"`` to avoid requiring the optional ``tzdata``
    package. ``None`` is returned unchanged. ``ValueError`` is raised for
    unsupported values.
    """

    if tz is None:
        return None
    if isinstance(tz, datetime.tzinfo):
        return tz
    if isinstance(tz, str):
        value = tz.strip()
        if not value:
            raise ValueError("timezone string cannot be empty")
        if value.upper() in {"UTC", "Z"}:
            return datetime.timezone.utc
        try:
            from zoneinfo import ZoneInfo
        except ModuleNotFoundError as exc:  # pragma: no cover - stdlib guard
            raise ValueError(
                "timezone strings require zoneinfo support"
            ) from exc
        try:
            return ZoneInfo(value)
        except Exception as exc:
            raise ValueError(f"unknown timezone: {tz!r}") from exc
    raise ValueError(f"unsupported timezone: {tz!r}")


def _import_smbus() -> types.ModuleType | types.SimpleNamespace | None:
    """Return an smbus-compatible module or ``None`` if unavailable."""

    try:  # defer import so tests can mock the module
        import smbus  # type: ignore
    except ModuleNotFoundError:
        try:
            from smbus2 import SMBus  # type: ignore

            smbus = types.SimpleNamespace(SMBus=SMBus)
        except ModuleNotFoundError:  # pragma: no cover - import error path
            msg = (
                "smbus module not found. Enable I2C and install 'i2c-tools' and "
                "'python3-smbus' or 'smbus2'."
            )
            gw.error(msg)
            print(msg)
            return None
    return smbus


def show(
    message: str,
    *,
    addr: int = 0x27,
    scroll: float = 0.0,
    hold: float = 0.0,
    wrap: bool = False,
    ratio: float | None = None,
) -> None:
    """Display *message* on the LCD.

    Parameters
    ----------
    message:
        Text to show.  ``[sigils]`` are resolved prior to display.  A
        newline character splits the message across the two lines of the
        display.  ``scroll`` determines the delay in seconds between each
        scroll step.  When ``scroll`` is ``0`` the message is static and only
        the first 16 characters of each line are shown.
    addr:
        I²C address of the backpack.  ``0x27`` and ``0x3F`` are common.
    scroll:
        Number of seconds to wait before scrolling one character. ``0`` (the
        default) disables scrolling.
    hold:
        Number of seconds to show the message before reverting to the
        previous one stored in ``work/lcd-last.txt``. ``0`` (the default)
        keeps the new message displayed.
    wrap:
        If ``True`` and ``scroll`` is ``0`` the message is word-wrapped
        across both lines of the display (16 characters per line).
    ratio:
        When ``scroll`` is non-zero and ``wrap`` is ``False``, show the same
        message on both rows scrolling at different speeds.  The top row's
        speed is divided by this value while the bottom row's speed is
        multiplied by it.  For example, ``ratio=2`` causes the bottom row to
        scroll the message four times while the top row scrolls it once.

    If the ``smbus`` module is missing, a helpful error message is logged and
    the function returns without attempting any I²C communication.
    """
    message = gw.resolve(message)
    last_path = gw.resource("work/lcd-last.txt", touch=True)
    try:
        prev = last_path.read_text(encoding="utf-8")
    except Exception:
        prev = ""

    smbus_mod = _import_smbus()
    if smbus_mod is None:
        return

    bus = smbus_mod.SMBus(1)
    _lcd_init(bus, addr)

    def _display(text: str, delay: float, do_wrap: bool, ratio: float | None) -> None:
        if delay > 0:
            if do_wrap:
                padding = " " * (LCD_WIDTH * 2)
                text = f"{padding}{text}{padding}"
                for idx in range(len(text) - (LCD_WIDTH * 2) + 1):
                    segment = text[idx : idx + LCD_WIDTH * 2]
                    _lcd_string(bus, addr, segment[:LCD_WIDTH], LCD_LINE_1)
                    _lcd_string(bus, addr, segment[LCD_WIDTH:], LCD_LINE_2)
                    time.sleep(delay)
            elif ratio is not None and ratio > 0:
                padding = " " * LCD_WIDTH
                text = f"{padding}{text}{padding}"
                segments = [
                    text[idx : idx + LCD_WIDTH]
                    for idx in range(len(text) - LCD_WIDTH + 1)
                ]
                top_delay = delay * ratio
                bottom_delay = delay / ratio
                total_time = 0.0
                top_next = 0.0
                bottom_next = 0.0
                top_idx = 0
                bottom_idx = 0
                top_total = len(segments) * top_delay
                while total_time < top_total:
                    if total_time >= top_next and top_idx < len(segments):
                        _lcd_string(
                            bus, addr, segments[top_idx], LCD_LINE_1
                        )
                        top_idx += 1
                        top_next += top_delay
                    if total_time >= bottom_next:
                        _lcd_string(
                            bus,
                            addr,
                            segments[bottom_idx % len(segments)],
                            LCD_LINE_2,
                        )
                        bottom_idx += 1
                        bottom_next += bottom_delay
                    next_event = min(top_next, bottom_next, top_total)
                    sleep_for = next_event - total_time
                    time.sleep(sleep_for)
                    total_time = next_event
            else:
                padding = " " * LCD_WIDTH
                text = f"{padding}{text}{padding}"
                for idx in range(len(text) - LCD_WIDTH + 1):
                    segment = text[idx : idx + LCD_WIDTH]
                    _lcd_string(bus, addr, segment, LCD_LINE_1)
                    time.sleep(delay)
        else:
            if do_wrap:
                import textwrap

                lines = textwrap.wrap(text, LCD_WIDTH)
                _lcd_string(bus, addr, lines[0] if lines else "", LCD_LINE_1)
                _lcd_string(
                    bus, addr, lines[1] if len(lines) > 1 else "", LCD_LINE_2
                )
            else:
                lines = text.split("\n", 1)
                _lcd_string(bus, addr, lines[0], LCD_LINE_1)
                if len(lines) > 1:
                    _lcd_string(bus, addr, lines[1], LCD_LINE_2)

    if ratio is not None and ratio <= 0:
        raise ValueError("ratio must be greater than 0")

    _display(message, scroll, wrap, ratio)

    if hold > 0:
        time.sleep(hold)
        _display(prev, 0, False, None)
    else:
        last_path.write_text(message, encoding="utf-8")


def clock(
    *,
    addr: int = 0x27,
    tz: str | datetime.tzinfo | None = None,
    interval: float = 1.0,
    updates: int | None = None,
) -> None:
    """Display a continuously updating clock on the LCD.

    The first row shows the weekday followed by the ISO formatted date (for
    example ``"Tue 2024-01-02"``) while the second row displays the time with
    seconds (``"03:04:05"``). The display refreshes every ``interval`` seconds
    until interrupted or until ``updates`` frames have been shown.
    """

    tzinfo = _coerce_timezone(tz)

    if interval <= 0:
        raise ValueError("interval must be greater than 0")
    if updates is not None:
        if updates < 0:
            raise ValueError("updates must be greater than or equal to 0")
        if updates == 0:
            return

    smbus_mod = _import_smbus()
    if smbus_mod is None:
        return

    bus = smbus_mod.SMBus(1)
    _lcd_init(bus, addr)

    shown = 0
    while True:
        if tzinfo is None:
            now = datetime.datetime.now()
        else:
            now = datetime.datetime.now(tz=tzinfo)
        top_line = f"{now:%a} {now.date().isoformat()}"
        bottom_line = now.strftime("%H:%M:%S")
        _lcd_string(bus, addr, top_line, LCD_LINE_1)
        _lcd_string(bus, addr, bottom_line, LCD_LINE_2)

        shown += 1
        if updates is not None and shown >= updates:
            break

        time.sleep(interval)


def brightness(level: int | float | bool | str, *, addr: int = 0x27) -> None:
    """Turn the LCD backlight on or off.

    The commonly used PCF8574 backpack only exposes a digital backlight pin,
    so brightness is effectively a binary choice.  Any value greater than
    zero (or truthy strings such as ``"on"``) enables the backlight while
    zero (or ``"off"``) disables it.
    """

    if isinstance(level, str):
        value = level.strip().lower()
        if value in {"on", "true", "yes"}:
            level = 1
        elif value in {"off", "false", "no"}:
            level = 0
        else:
            try:
                level = float(value)
            except ValueError as exc:
                raise ValueError(f"invalid brightness level: {level!r}") from exc

    try:
        is_on = float(level) > 0
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid brightness level: {level!r}") from exc

    global _backlight_mask
    _backlight_mask = LCD_BACKLIGHT if is_on else 0

    smbus_mod = _import_smbus()
    if smbus_mod is None:
        return

    bus = smbus_mod.SMBus(1)
    bus.write_byte(addr, _backlight_mask)


