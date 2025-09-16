"""Prototype helpers for passive infrared (PIR) sensors."""

from __future__ import annotations

import time

from gway.projects.sensor import _resolve_gpio


def sense_motion(
    *,
    pin: int = 17,
    gpio_module=None,
    settle_time: float = 2.0,
    interval: float = 0.5,
    max_checks: int | None = None,
) -> None:
    """Run a simple console prototype for a PIR motion sensor.

    Parameters
    ----------
    pin:
        BCM pin number connected to the sensor's digital output. Defaults to
        ``17`` (``IO17``).
    gpio_module:
        Optional GPIO-like module providing ``setmode``, ``setup``, ``input``
        and ``cleanup``. Defaults to :mod:`RPi.GPIO` (or :mod:`RPIO`) when
        available.
    settle_time:
        Seconds to wait after setting up the GPIO pin before polling. Defaults
        to ``2`` seconds to match common PIR warm-up requirements.
    interval:
        Seconds to wait between polls. Defaults to half a second.
    max_checks:
        Maximum number of polls to perform before returning. ``None`` means run
        indefinitely. This is primarily intended for testing.
    """

    GPIO = _resolve_gpio(gpio_module)
    if GPIO is None:
        return
    GPIO.setmode(getattr(GPIO, "BCM", GPIO.BOARD))
    GPIO.setup(pin, getattr(GPIO, "IN"))
    print("PIR Sensor Test (CTRL+C to exit)")
    if settle_time > 0:
        time.sleep(settle_time)
    checks = 0
    try:
        while max_checks is None or checks < max_checks:
            message = "⚡ Motion detected!" if GPIO.input(pin) else "... no motion"
            print(message)
            checks += 1
            if max_checks is not None and checks >= max_checks:
                break
            if interval > 0:
                time.sleep(interval)
    except KeyboardInterrupt:  # pragma: no cover - user interrupt
        print("Exiting...")
    finally:
        GPIO.cleanup(pin)
