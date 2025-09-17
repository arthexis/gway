"""Tests for RFID helpers."""

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
