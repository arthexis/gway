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

import time
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


def _lcd_toggle_enable(bus, addr: int, data: int) -> None:
    """Toggle enable bit to latch data."""
    time.sleep(E_DELAY)
    bus.write_byte(addr, data | ENABLE)
    time.sleep(E_PULSE)
    bus.write_byte(addr, data & ~ENABLE)
    time.sleep(E_DELAY)


def _lcd_byte(bus, addr: int, value: int, mode: int) -> None:
    """Send a single command or character byte."""
    high = mode | (value & 0xF0) | LCD_BACKLIGHT
    low = mode | ((value << 4) & 0xF0) | LCD_BACKLIGHT
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


def show(
    message: str,
    *,
    addr: int = 0x27,
    scroll: bool = False,
    ms: int = 2000,
) -> None:
    """Display *message* on the LCD.

    Parameters
    ----------
    message:
        Text to show.  ``[sigils]`` are resolved prior to display.  A
        newline character splits the message across the two lines of the
        display.  When ``scroll`` is true the message is scrolled across
        the first line.
    addr:
        I²C address of the backpack.  ``0x27`` and ``0x3F`` are common.
    scroll:
        Scroll the message instead of showing static text.
    ms:
        Delay in milliseconds between each scroll step.  Defaults to
        ``2000`` (2 seconds).

    Raises
    ------
    RuntimeError
        If the ``smbus`` module is not available.  Ensure the
        prerequisites above are completed.
    """
    message = gw.resolve(message)

    try:  # defer import so tests can mock the module
        import smbus  # type: ignore
    except ModuleNotFoundError as exc:  # pragma: no cover - import error path
        raise RuntimeError(
            "smbus module not found. Enable I2C and install "
            "'i2c-tools' and 'python3-smbus'."
        ) from exc

    bus = smbus.SMBus(1)
    _lcd_init(bus, addr)

    if scroll:
        delay = ms / 1000.0
        padding = " " * LCD_WIDTH
        text = f"{padding}{message}{padding}"
        for idx in range(len(text) - LCD_WIDTH + 1):
            segment = text[idx : idx + LCD_WIDTH]
            _lcd_string(bus, addr, segment, LCD_LINE_1)
            time.sleep(delay)
    else:
        lines = message.split("\n", 1)
        _lcd_string(bus, addr, lines[0], LCD_LINE_1)
        if len(lines) > 1:
            _lcd_string(bus, addr, lines[1], LCD_LINE_2)
