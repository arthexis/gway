"""Tests for RFID helpers."""

import sys
import types

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
