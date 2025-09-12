# file: projects/sensor.py
"""Sensor utilities including proximity watcher."""

from __future__ import annotations

from gway import gw


def watch_proximity(pin: int = 17, *, gpio_module=None, max_events: int | None = None) -> None:
    """Block and report when a proximity sensor on ``pin`` is triggered.

    Parameters
    ----------
    pin:
        BCM pin number wired to the sensor's digital output. Defaults to ``17``
        (``IO17``).
    gpio_module:
        Optional GPIO-like module providing ``setmode``, ``setup``, ``wait_for_edge``
        and ``cleanup``.  Defaults to :mod:`RPi.GPIO` when available.
    max_events:
        Maximum number of events to report before returning.  ``None`` means run
        indefinitely.  This is primarily intended for testing.
    """
    if gpio_module is None:
        try:  # pragma: no cover - hardware import
            import RPi.GPIO as GPIO  # type: ignore
            gpio_module = GPIO
        except Exception:  # pragma: no cover - hardware missing
            gw.error("RPi.GPIO not available; install it on a Raspberry Pi")
            print("Proximity sensor watch requires RPi.GPIO")
            return

    GPIO = gpio_module
    GPIO.setmode(getattr(GPIO, "BCM", GPIO.BOARD))
    GPIO.setup(pin, getattr(GPIO, "IN"))
    print(f"Watching proximity sensor on pin {pin}...")
    events = 0
    try:
        while max_events is None or events < max_events:
            # Wait for any edge; sensors usually pull the line high when triggered.
            GPIO.wait_for_edge(pin, getattr(GPIO, "BOTH", None))
            events += 1
            print("Proximity detected!")
    except KeyboardInterrupt:  # pragma: no cover - user interrupt
        print("Stopping proximity watch")
    finally:
        GPIO.cleanup(pin)
