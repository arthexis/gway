# file: projects/sensor.py
"""Sensor utilities including proximity watcher."""

from __future__ import annotations

import time

from gway import gw


def _resolve_gpio(gpio_module=None):
    """Return an available GPIO-like module.

    Tries :mod:`RPi.GPIO` first and falls back to :mod:`RPIO`. ``None`` is
    returned when neither library is available, in which case the caller should
    abort and warn the user.
    """
    if gpio_module is not None:
        return gpio_module
    try:  # pragma: no cover - hardware import
        import RPi.GPIO as GPIO  # type: ignore
        return GPIO
    except Exception:  # pragma: no cover - hardware missing
        try:  # pragma: no cover - hardware import
            import RPIO as GPIO  # type: ignore
            return GPIO
        except Exception:  # pragma: no cover - hardware missing
            gw.error("RPi.GPIO or RPIO not available; install one on a Raspberry Pi")
            print("Proximity sensor requires RPi.GPIO or RPIO")
            return None


def watch_proximity(pin: int = 17, *, gpio_module=None, max_events: int | None = None) -> None:
    """Block and report when a proximity sensor on ``pin`` is triggered.

    Parameters
    ----------
    pin:
        BCM pin number wired to the sensor's digital output. Defaults to ``17``
        (``IO17``).
    gpio_module:
        Optional GPIO-like module providing ``setmode``, ``setup``, ``wait_for_edge``
        and ``cleanup``.  Defaults to :mod:`RPi.GPIO` (or :mod:`RPIO`) when
        available.
    max_events:
        Maximum number of events to report before returning.  ``None`` means run
        indefinitely.  This is primarily intended for testing.
    """
    GPIO = _resolve_gpio(gpio_module)
    if GPIO is None:
        return
    gpio_module = GPIO
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


def proximity(
    pin: int = 17,
    *,
    gpio_module=None,
    interval: float = 2.0,
    max_checks: int | None = None,
) -> None:
    """Poll a proximity sensor and print simple indicators.

    A ``!`` is printed when the sensor reports activity, otherwise ``.`` is
    printed every ``interval`` seconds.  The function blocks until interrupted
    or ``max_checks`` has been reached.

    Parameters
    ----------
    pin:
        BCM pin number wired to the sensor's digital output. Defaults to ``17``
        (``IO17``).
    gpio_module:
        Optional GPIO-like module providing ``setmode``, ``setup``, ``input``
        and ``cleanup``.  Defaults to :mod:`RPi.GPIO` (or :mod:`RPIO`) when
        available.
    interval:
        Seconds to wait between sensor polls.  Defaults to ``2`` seconds.
    max_checks:
        Maximum number of polls to perform before returning. ``None`` means run
        indefinitely. This is primarily intended for testing.
    """
    GPIO = _resolve_gpio(gpio_module)
    if GPIO is None:
        return
    gpio_module = GPIO
    GPIO.setmode(getattr(GPIO, "BCM", GPIO.BOARD))
    GPIO.setup(pin, getattr(GPIO, "IN"))
    checks = 0
    try:
        while max_checks is None or checks < max_checks:
            symbol = "!" if GPIO.input(pin) else "."
            print(symbol, end="", flush=True)
            time.sleep(interval)
            checks += 1
        print()
    except KeyboardInterrupt:  # pragma: no cover - user interrupt
        print("\nStopping proximity polling")
    finally:
        GPIO.cleanup(pin)


def motion(
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
    gpio_module = GPIO
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
