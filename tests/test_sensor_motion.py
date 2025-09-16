import io
from contextlib import redirect_stdout

from gway import gw


def test_motion_reports_sequence():
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
        gw.sensor.motion(
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


def test_motion_handles_keyboard_interrupt(monkeypatch):
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

    monkeypatch.setattr("gway.projects.sensor.time.sleep", raising_sleep)

    gpio = FakeGPIO()
    buf = io.StringIO()
    with redirect_stdout(buf):
        gw.sensor.motion(
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
