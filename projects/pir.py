"""Prototype helpers for passive infrared (PIR) sensors."""

from __future__ import annotations

import time

from gway.projects.sensor import _resolve_gpio


def sense_motion(
    *,
    pin: int = 17,
    gpio_module=None,
    settle_time: float = 2.0,
    interval: float = 2.0,
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
        Seconds to wait between polls. Defaults to two seconds.
    max_checks:
        Maximum number of polls to perform before returning. ``None`` means run
        indefinitely. This is primarily intended for testing.
    """

    GPIO = _resolve_gpio(gpio_module)
    if GPIO is None:
        return

    mode = getattr(GPIO, "BCM", None)
    if mode is None:
        mode = getattr(GPIO, "BOARD", None)
    if mode is None:
        mode = "BCM"
    GPIO.setmode(mode)
    setup_kwargs = {}
    pull_down = getattr(GPIO, "PUD_DOWN", None)
    if pull_down is not None:
        setup_kwargs["pull_up_down"] = pull_down
    GPIO.setup(pin, getattr(GPIO, "IN"), **setup_kwargs)
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


def calibrate(
    *,
    pin: int = 17,
    gpio_module=None,
    warmup_time: float = 60.0,
    sample_interval: float = 0.02,
    max_transitions: int | None = None,
    max_runtime: float | None = None,
) -> None:
    """Interactively tune a PIR sensor by reporting edge transitions.

    The helper mirrors the advice from Raspberry Pi community experts:

    * enable the built-in pull-down resistor so the ``LOW`` state stays stable
      during calibration,
    * let the sensor warm up to avoid spurious oscillations, and
    * watch for actual state changes instead of repeatedly polling the same
      value so you can correlate dial adjustments with motion events.

    Parameters
    ----------
    pin:
        BCM pin number connected to the sensor's digital output. Defaults to
        ``17`` (``IO17``).
    gpio_module:
        Optional GPIO-like module providing ``setmode``, ``setup``, ``input``,
        ``cleanup`` and, ideally, ``PUD_DOWN``. Defaults to :mod:`RPi.GPIO`
        (or :mod:`RPIO`) when available.
    warmup_time:
        Seconds to let the sensor stabilise after powering on. Most PIR modules
        need 30–60 seconds; the default uses 60 seconds to avoid false pulses.
    sample_interval:
        Seconds to wait between sensor polls once calibration begins. Defaults
        to ``0.02`` seconds, mirroring the lightweight loop in the reference
        calibration script.
    max_transitions:
        Maximum number of state changes to report before returning. ``None``
        means run until interrupted. This parameter is intended for testing.
    max_runtime:
        Maximum number of seconds to watch before automatically exiting. Use
        this for scripted runs where ``KeyboardInterrupt`` is not convenient.
    """

    GPIO = _resolve_gpio(gpio_module)
    if GPIO is None:
        return

    mode = getattr(GPIO, "BCM", None)
    if mode is None:
        mode = getattr(GPIO, "BOARD", None)
    if mode is None:
        mode = "BCM"
    GPIO.setmode(mode)
    setup_kwargs = {}
    pull_down = getattr(GPIO, "PUD_DOWN", None)
    if pull_down is not None:
        setup_kwargs["pull_up_down"] = pull_down
    GPIO.setup(pin, getattr(GPIO, "IN"), **setup_kwargs)

    print("PIR Calibration (CTRL+C to exit)")
    if warmup_time > 0:
        print(f"Warming up for {warmup_time:.0f}s – keep still.")
        time.sleep(warmup_time)
    print("Watching for motion state changes. Adjust TIME and SENS slowly.")

    last_state = GPIO.input(pin)
    last_change = time.time()
    start_time = last_change
    transitions = 0
    print(f"Initial state: {'MOTION' if last_state else 'no motion'}")

    try:
        while True:
            if max_runtime is not None:
                elapsed = time.time() - start_time
                if elapsed >= max_runtime:
                    print("Reached maximum runtime; stopping calibration.")
                    break

            current_state = GPIO.input(pin)
            if current_state != last_state:
                now = time.time()
                duration = now - last_change
                timestamp = time.strftime("%H:%M:%S")
                print(
                    f"{timestamp}  {'MOTION' if current_state else 'no motion'}  "
                    f"(state held for {duration:.1f}s)"
                )
                last_state = current_state
                last_change = now
                transitions += 1
                if max_transitions is not None and transitions >= max_transitions:
                    break

            if sample_interval > 0:
                time.sleep(sample_interval)
    except KeyboardInterrupt:  # pragma: no cover - user interrupt
        print("Calibration interrupted")
    finally:
        GPIO.cleanup(pin)


# Backwards-compatible alias to align with CLI naming conventions
sense = sense_motion
