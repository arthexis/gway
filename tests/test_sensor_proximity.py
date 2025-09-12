import io
from contextlib import redirect_stdout
from gway import gw


def test_watch_proximity_reports_events():
    class FakeGPIO:
        BCM = "BCM"
        IN = "IN"
        BOTH = "BOTH"
        def __init__(self):
            self.cleaned = []
            self.wait_calls = 0
        def setmode(self, mode):
            self.mode = mode
        def setup(self, pin, mode):
            self.pin = pin
            self.mode_set = mode
        def wait_for_edge(self, pin, edge):
            self.wait_calls += 1
            if self.wait_calls > 1:
                raise AssertionError("should not block after max_events")
        def cleanup(self, pin):
            self.cleaned.append(pin)

    gpio = FakeGPIO()
    buf = io.StringIO()
    with redirect_stdout(buf):
        gw.sensor.watch_proximity(gpio_module=gpio, max_events=1)

    out = buf.getvalue()
    assert "Proximity detected" in out
    assert gpio.cleaned == [17]
