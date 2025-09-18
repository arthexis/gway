"""Tests for RFID helpers."""

import sys
import types

import pytest

from projects import rfid


EXPECTED_PINOUT = {
    "SDA": "CE0 (GPIO8, physical pin 24)",
    "SCK": "SCLK (GPIO11, physical pin 23)",
    "MOSI": "MOSI (GPIO10, physical pin 19)",
    "MISO": "MISO (GPIO9, physical pin 21)",
    "IRQ": "GPIO4 (physical pin 7)",
    "GND": "GND (physical pin 6)",
    "RST": "GPIO25 (physical pin 22)",
    "3v3": "3V3 (physical pin 1)",
}


def test_pinout_matches_expected_mapping():
    """Ensure the exposed pinout documents the expected wiring."""

    assert rfid.pinout() == EXPECTED_PINOUT


def test_pinout_returns_copy():
    """The wiring map should be copy-on-return to prevent accidental edits."""

    mapping = rfid.pinout()
    mapping["SDA"] = "modified"
    assert rfid.pinout()["SDA"] == EXPECTED_PINOUT["SDA"]


def test_scan_handles_missing_spi_interface(monkeypatch, capsys):
    """A missing SPI device should not raise and should explain the issue."""

    class FakeReader:
        def __init__(self):
            raise FileNotFoundError("/dev/spidev0.0")

    _install_fake_rfid_dependencies(monkeypatch, FakeReader)
    monkeypatch.setattr(rfid.os.path, "exists", lambda path: True)

    rfid.scan()
    captured = capsys.readouterr()
    assert "RFID hardware interface not found" in captured.out


def test_scan_explains_when_no_spi_nodes_exist(monkeypatch, capsys):
    """If no ``/dev/spidev*`` nodes exist the CLI should explain how to enable SPI."""

    class FakeReader:
        def __init__(self):  # pragma: no cover - should not run
            raise AssertionError("reader should not be constructed when SPI is missing")

    _install_fake_rfid_dependencies(monkeypatch, FakeReader)
    monkeypatch.setattr(rfid.os.path, "exists", lambda path: False)
    monkeypatch.setattr(rfid.glob, "glob", lambda pattern: [])

    rfid.scan()
    captured = capsys.readouterr()
    assert "no /dev/spidev* nodes" in captured.out
    assert "Enable SPI" in captured.out


def test_scan_lists_available_spi_candidates(monkeypatch, capsys):
    """Surface alternative SPI nodes so users can rewire or extend the helper."""

    class FakeReader:
        def __init__(self):  # pragma: no cover - should not run
            raise AssertionError("reader should not be constructed when SPI is missing")

    _install_fake_rfid_dependencies(monkeypatch, FakeReader)
    monkeypatch.setattr(rfid.os.path, "exists", lambda path: False)
    monkeypatch.setattr(
        rfid.glob,
        "glob",
        lambda pattern: ["/dev/spidev0.1", "/dev/spidev1.0", "/dev/spidev0.0"],
    )

    rfid.scan()
    captured = capsys.readouterr()
    assert "Detected SPI interfaces" in captured.out
    assert "/dev/spidev0.1" in captured.out


def test_scan_reports_permission_errors(monkeypatch, capsys):
    """Permission issues should hint at running with sudo or joining the SPI group."""

    class FakeReader:
        def __init__(self):
            raise PermissionError("[Errno 13] Permission denied: '/dev/spidev0.0'")

    _install_fake_rfid_dependencies(monkeypatch, FakeReader)
    monkeypatch.setattr(rfid.os.path, "exists", lambda path: True)

    rfid.scan()
    captured = capsys.readouterr()
    assert "permission denied" in captured.out.lower()
    assert "spi` group" in captured.out


def test_scan_returns_uid_after_threshold(monkeypatch, capsys):
    """Stop automatically once the same card has been detected enough times."""

    class FakeReader:
        def __init__(self):
            self.calls = 0
            self.responses = [
                (None, ""),
                (987654321, " first "),
                (None, ""),
                (987654321, " second "),
            ]

        def read_no_block(self):
            if self.calls >= len(self.responses):
                result = self.responses[-1]
            else:
                result = self.responses[self.calls]
            self.calls += 1
            return result

    _prepare_scan_test(monkeypatch, FakeReader)

    result = rfid.scan(after=2)

    captured = capsys.readouterr()
    assert result == 987654321
    assert captured.out.count("Card ID: 987654321") == 2


def test_scan_once_returns_uid(monkeypatch, capsys):
    """The ``--once`` flag should stop after the first successful read."""

    class FakeReader:
        def read_no_block(self):
            return (555444333, " payload ")

    _prepare_scan_test(monkeypatch, FakeReader)

    result = rfid.scan(once=True)

    captured = capsys.readouterr()
    assert result == 555444333
    assert captured.out.count("Card ID: 555444333") == 1


def test_scan_once_rejects_conflicting_after():
    """Using ``--once`` with a non-matching ``--after`` value should fail."""

    with pytest.raises(ValueError):
        rfid.scan(after=2, once=True)


def test_scan_wait_timeout_stops_scan(monkeypatch, capsys):
    """Automatically exit when the wait timeout elapses."""

    class FakeReader:
        last_instance = None

        def __init__(self):
            type(self).last_instance = self
            self.calls = 0

        def read_no_block(self):
            self.calls += 1
            return (None, "")

    fake_clock = _prepare_scan_test(monkeypatch, FakeReader)

    result = rfid.scan(wait="0.3")

    captured = capsys.readouterr()
    assert result is None
    assert "Card ID:" not in captured.out
    assert FakeReader.last_instance.calls == 3
    assert fake_clock.now == pytest.approx(0.3)


def test_scan_rejects_invalid_wait(monkeypatch):
    """``wait`` must be a positive numeric value."""

    monkeypatch.setattr(
        rfid,
        "_initialize_reader",
        lambda: pytest.fail("_initialize_reader should not run on invalid wait"),
    )

    with pytest.raises(ValueError):
        rfid.scan(wait=0)

    with pytest.raises(TypeError):
        rfid.scan(wait=True)


def _install_fake_rfid_dependencies(monkeypatch, reader_cls):
    """Install stub modules so ``rfid.scan`` can be exercised without hardware."""

    fake_mfrc522 = types.SimpleNamespace(SimpleMFRC522=reader_cls)
    fake_rpi = types.ModuleType("RPi")
    fake_gpio = types.ModuleType("RPi.GPIO")
    fake_gpio.cleanup = lambda: None
    fake_rpi.GPIO = fake_gpio

    monkeypatch.setitem(sys.modules, "mfrc522", fake_mfrc522)
    monkeypatch.setitem(sys.modules, "RPi", fake_rpi)
    monkeypatch.setitem(sys.modules, "RPi.GPIO", fake_gpio)


def _prepare_scan_test(monkeypatch, reader_cls):
    """Set up the environment for scan tests that expect successful reads."""

    _install_fake_rfid_dependencies(monkeypatch, reader_cls)
    monkeypatch.setattr(rfid.os.path, "exists", lambda path: True)
    monkeypatch.setattr(rfid.select, "select", lambda *args: ([], [], []))

    class FakeClock:
        def __init__(self):
            self.now = 0.0

        def monotonic(self):
            return self.now

        def sleep(self, duration):
            self.now += duration

    fake_clock = FakeClock()
    monkeypatch.setattr(rfid.time, "monotonic", fake_clock.monotonic)
    monkeypatch.setattr(rfid.time, "sleep", fake_clock.sleep)
    return fake_clock


def _prepare_write_test(monkeypatch, reader_cls):
    """Utility to install fake RFID dependencies and common patches."""

    _install_fake_rfid_dependencies(monkeypatch, reader_cls)
    monkeypatch.setattr(rfid.os.path, "exists", lambda path: True)
    monkeypatch.setattr(rfid.time, "sleep", lambda duration: None)


def test_write_waits_for_card_and_writes_uid(monkeypatch, capsys):
    """The writer should poll until a card is detected, then program it."""

    class FakeWriter:
        last_instance = None

        def __init__(self):
            type(self).last_instance = self
            self.write_calls = []
            self.reads = 0

        def read_no_block(self):
            self.reads += 1
            if self.reads < 2:
                return (None, "")
            return (123456789, "old")

        def write(self, text):
            self.write_calls.append(text)

    _prepare_write_test(monkeypatch, FakeWriter)

    result = rfid.write(uid=42, poll_interval=0)

    captured = capsys.readouterr()
    assert "Wrote UID 42 to card 123456789." in captured.out
    assert result == {"card_id": 123456789, "written_uid": 42}
    assert FakeWriter.last_instance.write_calls == ["42"]


def test_write_auto_increment_true_increments_uid(monkeypatch, capsys):
    """A truthy auto-increment flag should increment the UID by one."""

    class FakeWriter:
        last_instance = None

        def __init__(self):
            type(self).last_instance = self

        def read_no_block(self):
            return (555, "old")

        def write(self, text):
            self.last_written = text

    _prepare_write_test(monkeypatch, FakeWriter)

    result = rfid.write(uid=99, auto_increment=True, poll_interval=0)

    assert FakeWriter.last_instance.last_written == "100"
    assert result["written_uid"] == 100
    assert result["next_uid"] == 101
    captured = capsys.readouterr()
    assert "Ready to write UID 100" in captured.out
    assert "Next UID: 101" in captured.out


def test_write_auto_increment_accepts_numeric_string(monkeypatch):
    """Supplying a numeric string for auto-increment should succeed."""

    class FakeWriter:
        last_instance = None

        def __init__(self):
            type(self).last_instance = self

        def read_no_block(self):
            return (321, "old")

        def write(self, text):
            self.last_written = text

    _prepare_write_test(monkeypatch, FakeWriter)

    result = rfid.write(uid="10", auto_increment="5", poll_interval=0)

    assert FakeWriter.last_instance.last_written == "15"
    assert result == {"card_id": 321, "written_uid": 15, "next_uid": 20}


def test_write_rejects_invalid_auto_increment(monkeypatch):
    """Non-numeric strings for auto-increment should raise an informative error."""

    class FakeWriter:
        def __init__(self):
            pass

        def read_no_block(self):  # pragma: no cover - should not be called
            raise AssertionError("read_no_block should not run on invalid input")

        def write(self, text):  # pragma: no cover - should not be called
            raise AssertionError("write should not run on invalid input")

    _prepare_write_test(monkeypatch, FakeWriter)

    with pytest.raises(ValueError):
        rfid.write(uid=1, auto_increment="banana")
