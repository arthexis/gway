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

import shlex
import subprocess
import time
import types
from pathlib import Path
from textwrap import dedent
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
    scroll: float = 0.0,
    hold: float = 0.0,
    wrap: bool = False,
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

    If the ``smbus`` module is missing, a helpful error message is logged and
    the function returns without attempting any I²C communication.
    """
    message = gw.resolve(message)
    last_path = gw.resource("work/lcd-last.txt", touch=True)
    try:
        prev = last_path.read_text(encoding="utf-8")
    except Exception:
        prev = ""

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
            return

    bus = smbus.SMBus(1)
    _lcd_init(bus, addr)

    def _display(text: str, delay: float, do_wrap: bool) -> None:
        if delay > 0:
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

    _display(message, scroll, wrap)

    if hold > 0:
        time.sleep(hold)
        _display(prev, 0, False)
    else:
        last_path.write_text(message, encoding="utf-8")


def boot(
    message: str | None = None,
    *,
    remove: bool = False,
    path: str | Path = "/etc/systemd/system/gway-lcd-boot.service",
) -> None:
    """Install or remove a boot-time service displaying ``message``.

    When installed, a systemd ``oneshot`` service is created that calls
    :func:`show` at startup.  Re-installing replaces any existing service so
    only one boot message is active at a time.

    Parameters
    ----------
    message:
        Text to display at boot.  ``[sigils]`` are resolved at runtime.  If
        ``None`` and ``remove`` is ``False`` the service is removed.
    remove:
        Uninstall the service instead of installing.
    path:
        Optional override for the service file path.  Defaults to the system
        location.
    """

    svc_path = Path(path)
    name = svc_path.name

    if remove or not message:
        if svc_path.exists():
            subprocess.run(["systemctl", "disable", "--now", name], check=False)
            try:
                svc_path.unlink()
            except FileNotFoundError:
                pass
            subprocess.run(["systemctl", "daemon-reload"], check=False)
        return

    if svc_path.exists():
        subprocess.run(["systemctl", "disable", "--now", name], check=False)

    cmd = f"/usr/bin/env gway lcd show {shlex.quote(message)}"
    unit = dedent(
        f"""
        [Unit]
        Description=GWAY LCD boot message
        After=multi-user.target

        [Service]
        Type=oneshot
        ExecStart={cmd}

        [Install]
        WantedBy=multi-user.target
        """
    ).strip() + "\n"

    svc_path.write_text(unit)
    subprocess.run(["systemctl", "daemon-reload"], check=False)
    subprocess.run(["systemctl", "enable", name], check=False)
    subprocess.run(["systemctl", "restart", name], check=False)
