import io
import unittest
from contextlib import redirect_stdout

from gway import gw
from gway.builtins import is_test_flag


@unittest.skipUnless(
    is_test_flag("sensors"),
    "Sensor tests disabled (enable with --flags sensors)",
)
def test_sense_motion_reports_sequence():
    class FakeGPIO:
        BCM = "BCM"
        IN = "IN"

        def __init__(self, readings):
            self.readings = readings
            self.cleaned = []

        def setmode(self, mode):
            self.mode = mode

        def setup(self, pin, mode):
            self.pin = pin
            self.mode_set = mode

        def input(self, pin):
            return self.readings.pop(0)

        def cleanup(self, pin):
            self.cleaned.append(pin)

    gpio = FakeGPIO([0, 1, 0])
    buf = io.StringIO()
    with redirect_stdout(buf):
        gw.pir.sense_motion(
            gpio_module=gpio,
            settle_time=0.0,
            interval=0.0,
            max_checks=3,
        )

    lines = buf.getvalue().splitlines()
    assert lines == [
        "PIR Sensor Test (CTRL+C to exit)",
        "... no motion",
        "⚡ Motion detected!",
        "... no motion",
    ]
    assert gpio.cleaned == [17]


@unittest.skipUnless(
    is_test_flag("sensors"),
    "Sensor tests disabled (enable with --flags sensors)",
)
def test_sense_motion_handles_keyboard_interrupt(monkeypatch):
    class FakeGPIO:
        BCM = "BCM"
        IN = "IN"

        def __init__(self):
            self.cleaned = []

        def setmode(self, mode):
            self.mode = mode

        def setup(self, pin, mode):
            self.pin = pin
            self.mode_set = mode

        def input(self, pin):
            return 0

        def cleanup(self, pin):
            self.cleaned.append(pin)

    def raising_sleep(seconds):
        raise KeyboardInterrupt

    monkeypatch.setattr("projects.pir.time.sleep", raising_sleep)

    gpio = FakeGPIO()
    buf = io.StringIO()
    with redirect_stdout(buf):
        gw.pir.sense_motion(
            gpio_module=gpio,
            settle_time=0.0,
            interval=1.0,
        )

    lines = buf.getvalue().splitlines()
    assert lines == [
        "PIR Sensor Test (CTRL+C to exit)",
        "... no motion",
        "Exiting...",
    ]
    assert gpio.cleaned == [17]


@unittest.skipUnless(
    is_test_flag("sensors"),
    "Sensor tests disabled (enable with --flags sensors)",
)
def test_calibrate_reports_transitions(monkeypatch):
    class FakeGPIO:
        BCM = "BCM"
        IN = "IN"
        PUD_DOWN = "PUD_DOWN"

        def __init__(self, readings):
            self.readings = list(readings)
            self.cleaned = []
            self.setup_kwargs = None
            self.last_value = 0

        def setmode(self, mode):
            self.mode = mode

        def setup(self, pin, mode, **kwargs):
            self.pin = pin
            self.mode_set = mode
            self.setup_kwargs = kwargs

        def input(self, pin):
            if self.readings:
                self.last_value = self.readings.pop(0)
            return self.last_value

        def cleanup(self, pin):
            self.cleaned.append(pin)

    class FakeTime:
        def __init__(self):
            self.current = 0.0

        def time(self):
            return self.current

        def sleep(self, seconds):
            self.current += seconds

        def strftime(self, fmt):
            return "00:00:00"

    fake_time = FakeTime()
    monkeypatch.setattr("projects.pir.time", fake_time)

    gpio = FakeGPIO([0, 1, 1, 0, 0])
    buf = io.StringIO()
    with redirect_stdout(buf):
        gw.pir.calibrate(
            gpio_module=gpio,
            warmup_time=0.0,
            sample_interval=0.02,
            max_transitions=2,
        )

    lines = buf.getvalue().splitlines()
    assert lines[:3] == [
        "PIR Calibration (CTRL+C to exit)",
        "Watching for motion state changes. Adjust TIME and SENS slowly.",
        "Initial state: no motion",
    ]
    assert lines[3].endswith("MOTION  (state held for 0.0s)")
    assert lines[4].endswith("no motion  (state held for 0.0s)")
    assert gpio.cleaned == [17]
    assert gpio.setup_kwargs == {"pull_up_down": "PUD_DOWN"}
