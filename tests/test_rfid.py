"""Tests for RFID helpers."""

import csv
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

    poll_events = [
        None,
        (987654321, (1, 2, 3, 4, 5), " first "),
        None,
        (987654321, (1, 2, 3, 4, 5), " second "),
    ]

    _prepare_scan_test(monkeypatch, poll_events)

    result = rfid.scan(after=2)

    captured = capsys.readouterr()
    assert result == 987654321
    assert captured.out.count("Card ID: 987654321") == 2


def test_start_trigger_runs_recipe_when_card_detected(monkeypatch, capsys):
    reader = types.SimpleNamespace()
    gpio = types.SimpleNamespace(cleanup=lambda: None)

    monkeypatch.setattr(rfid, "_initialize_reader", lambda: (reader, gpio))
    monkeypatch.setattr(rfid.os.path, "exists", lambda path: True)

    events = [(4242, (1, 2, 3, 4), "payload")]

    def fake_poll(_reader):
        return events.pop(0) if events else None

    times = iter([0.0, 1.0, 2.0])
    monkeypatch.setattr(rfid, "_poll_for_card", fake_poll)
    monkeypatch.setattr(rfid.time, "monotonic", lambda: next(times))
    monkeypatch.setattr(rfid.time, "sleep", lambda duration: None)

    triggered = {}

    def fake_run_recipe(trigger, *, section=None, RFID_UID):
        triggered.update({
            "trigger": trigger,
            "section": section,
            "uid": RFID_UID,
        })
        raise KeyboardInterrupt

    monkeypatch.setattr(rfid.gw, "run_recipe", fake_run_recipe)

    rfid.start_trigger(trigger="custom", section="# part", debounce=0, poll_interval=0.1)

    captured = capsys.readouterr()
    assert triggered == {"trigger": "custom", "section": "# part", "uid": "4242"}
    assert "Triggering recipe 'custom' for UID 4242" in captured.out
    assert "RFID trigger stopped." in captured.out


def test_scan_logs_detected_cards_to_default_csv(monkeypatch, tmp_path, capsys):
    """Enabling ``--csv`` should write detections to the default CSV file."""

    poll_events = [
        (111111111, (1, 2, 3, 4, 5), " first "),
        (111111111, (1, 2, 3, 4, 5), " second "),
    ]

    _prepare_scan_test(monkeypatch, poll_events)
    _install_fake_datetime(monkeypatch, [
        "2023-01-01T00:00:01",
        "2023-01-01T00:00:02",
    ])
    _install_fake_resource(monkeypatch, tmp_path)

    result = rfid.scan(after=2, csv=True)

    csv_path = tmp_path / "work" / "rfid" / rfid.DEFAULT_CSV_FILENAME
    assert csv_path.exists()
    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))

    assert result == 111111111
    assert rows == [
        ["timestamp", "card_id", "text"],
        ["2023-01-01T00:00:01", "111111111", "first"],
        ["2023-01-01T00:00:02", "111111111", "second"],
    ]

    captured = capsys.readouterr()
    assert f"Logging scans to {csv_path}" in captured.out


def test_scan_supports_custom_csv_path(monkeypatch, tmp_path):
    """Supplying a custom CSV target should log detections to that file."""

    poll_events = [(222333444, (5, 4, 3, 2, 1), " payload ")]

    _prepare_scan_test(monkeypatch, poll_events)
    _install_fake_datetime(monkeypatch, ["2024-02-02T12:34:56"])
    _install_fake_resource(monkeypatch, tmp_path)

    result = rfid.scan(once=True, csv="custom/log.csv")

    csv_path = tmp_path / "work" / "custom" / "log.csv"
    assert csv_path.exists()
    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))

    assert result == 222333444
    assert rows == [
        ["timestamp", "card_id", "text"],
        ["2024-02-02T12:34:56", "222333444", "payload"],
    ]


def test_scan_rejects_invalid_csv_argument(monkeypatch):
    """Non-path CSV arguments should raise an informative error."""

    monkeypatch.setattr(
        rfid,
        "_initialize_reader",
        lambda: pytest.fail("_initialize_reader should not run on invalid csv"),
    )

    with pytest.raises(TypeError):
        rfid.scan(csv=1234)


def test_scan_once_returns_uid(monkeypatch, capsys):
    """The ``--once`` flag should stop after the first successful read."""

    poll_events = [(555444333, (9, 9, 9, 9, 9), " payload ")]

    _prepare_scan_test(monkeypatch, poll_events)

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

    poll_events = [None, None, None]
    _reader, fake_poll = _prepare_scan_test(monkeypatch, poll_events)

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

    result = rfid.scan(wait="0.3")

    captured = capsys.readouterr()
    assert result is None
    assert "Card ID:" not in captured.out
    assert fake_poll.call_count == 3
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


def test_scan_prints_block_data_with_guessed_key(monkeypatch, capsys):
    """Block output should note when a guessed key succeeded."""

    poll_events = [(123456789, (1, 2, 3, 4, 5), " ")]
    block_results = [
        rfid.BlockReadResult(
            block=1,
            data=(0x41, 0x42, 0x43),
            key_type="B",
            key_hex="A0A1A2A3A4A5",
            guessed=True,
        )
    ]

    _prepare_scan_test(monkeypatch, poll_events, block_sequences=[block_results])

    rfid.scan(block=1, once=True)

    captured = capsys.readouterr()
    assert "Card ID: 123456789" in captured.out
    assert "Block 01 (Key B A0A1A2A3A4A5 guessed): 41 42 43" in captured.out


def test_scan_reports_block_authentication_failure(monkeypatch, capsys):
    """Failed authentication should surface the relevant message."""

    poll_events = [(222333444, (9, 8, 7, 6, 5), " ")]
    block_results = [
        rfid.BlockReadResult(
            block=5,
            error="authentication failed using provided and default keys",
            guess_attempted=True,
        )
    ]

    _prepare_scan_test(monkeypatch, poll_events, block_sequences=[block_results])

    rfid.scan(block=5, once=True)

    captured = capsys.readouterr()
    assert "Card ID: 222333444" in captured.out
    assert "Block 05: authentication failed using provided and default keys." in captured.out


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


def _prepare_scan_test(
    monkeypatch,
    poll_events,
    *,
    block_sequences=None,
):
    """Set up the environment for scan tests that expect successful reads."""

    reader = types.SimpleNamespace()
    gpio = types.SimpleNamespace(cleanup=lambda: None)
    monkeypatch.setattr(rfid, "_initialize_reader", lambda: (reader, gpio))
    monkeypatch.setattr(rfid.os.path, "exists", lambda path: True)
    monkeypatch.setattr(rfid.select, "select", lambda *args: ([], [], []))

    events_iter = iter(poll_events)

    def fake_poll(_reader):
        fake_poll.call_count += 1
        try:
            return next(events_iter)
        except StopIteration:
            return None

    fake_poll.call_count = 0
    monkeypatch.setattr(rfid, "_poll_for_card", fake_poll)

    if block_sequences is None:
        monkeypatch.setattr(rfid, "_read_blocks", lambda *args, **kwargs: [])
    else:
        block_iter = iter(block_sequences)

        def fake_read_blocks(*args, **kwargs):
            try:
                return next(block_iter)
            except StopIteration:
                return []

        monkeypatch.setattr(rfid, "_read_blocks", fake_read_blocks)

    monkeypatch.setattr(rfid.time, "sleep", lambda duration: None)
    return reader, fake_poll


def _install_fake_resource(monkeypatch, base_path):
    """Patch ``gw.resource`` to operate within a temporary directory."""

    def fake_resource(*parts, touch=False, check=False, text=False, dir=False):
        path = base_path.joinpath(*parts)
        if dir:
            path.mkdir(parents=True, exist_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            if touch and not path.exists():
                path.touch()
        if text:
            return path.read_text(encoding="utf-8")
        return path

    monkeypatch.setattr(rfid.gw, "resource", fake_resource)


def _install_fake_datetime(monkeypatch, timestamps):
    """Patch ``datetime.now`` to return predetermined ISO timestamps."""

    class _FakeTimestamp:
        def __init__(self, value):
            self._value = value

        def isoformat(self):
            return self._value

    class _FakeDatetime:
        _values = list(timestamps)
        _index = 0

        @classmethod
        def now(cls):
            if cls._index >= len(cls._values):
                raise AssertionError("datetime.now called more times than expected")
            value = cls._values[cls._index]
            cls._index += 1
            return _FakeTimestamp(value)

    monkeypatch.setattr(rfid.dt, "datetime", _FakeDatetime)


class _BlockTestChip:
    """Helper to emulate block authentication for ``_read_blocks`` tests."""

    MI_OK = 0
    PICC_AUTHENT1A = "A"
    PICC_AUTHENT1B = "B"

    def __init__(self, expected_keys, block_payloads):
        self.expected_keys = expected_keys
        self.block_payloads = block_payloads
        self.stop_calls = 0
        self.auth_calls = []
        self.select_calls = []

    def MFRC522_SelectTag(self, uid):
        self.select_calls.append(tuple(uid))

    def MFRC522_Auth(self, mode, block, key, uid):
        self.auth_calls.append((mode, block, tuple(key)))
        key_type = "A" if mode == self.PICC_AUTHENT1A else "B"
        sector = block // 4
        expected = self.expected_keys.get((key_type, sector))
        if expected and tuple(key) == expected:
            return self.MI_OK
        return 1

    def MFRC522_Read(self, block):
        return list(self.block_payloads.get(block, []))

    def MFRC522_StopCrypto1(self):
        self.stop_calls += 1


def _make_block_reader(expected_keys, block_payloads):
    return types.SimpleNamespace(READER=_BlockTestChip(expected_keys, block_payloads))


def test_read_blocks_uses_provided_key_a():
    """Reading a block with a supplied key A should succeed."""

    key_a = (0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5)
    reader = _make_block_reader({("A", 1): key_a}, {4: [0x10, 0x20]})
    key_candidates = {"A": [(key_a, False)], "B": []}

    results = rfid._read_blocks(
        reader,
        (1, 2, 3, 4, 5),
        [4],
        key_candidates,
        guess_mode=False,
    )

    assert len(results) == 1
    result = results[0]
    assert result.block == 4
    assert result.key_type == "A"
    assert result.key_hex == "A0A1A2A3A4A5"
    assert result.data == (0x10, 0x20)
    assert not result.guessed
    assert reader.READER.stop_calls == 1


def test_read_blocks_guesses_key_b():
    """Default keys should be attempted when none are provided."""

    guessed_key = rfid.COMMON_MIFARE_CLASSIC_KEYS[1]
    reader = _make_block_reader({("B", 2): guessed_key}, {8: [0xAA]})
    key_candidates, guess_mode = rfid._prepare_key_candidates(
        None, None, guess_defaults=True
    )

    results = rfid._read_blocks(
        reader,
        (9, 8, 7, 6, 5),
        [8],
        key_candidates,
        guess_mode=guess_mode,
    )

    assert len(results) == 1
    result = results[0]
    assert result.key_type == "B"
    assert result.guessed is True
    assert result.key_hex == "A0A1A2A3A4A5"
    assert result.data == (0xAA,)


def test_read_blocks_reports_failure_when_no_keys_match():
    """When no keys succeed an informative error message should be returned."""

    reader = _make_block_reader({("A", 0): (0x01, 0x02, 0x03, 0x04, 0x05, 0x06)}, {})
    key_candidates, guess_mode = rfid._prepare_key_candidates(
        None, None, guess_defaults=True
    )

    results = rfid._read_blocks(
        reader,
        (0, 0, 0, 0, 1),
        [0],
        key_candidates,
        guess_mode=guess_mode,
    )

    assert len(results) == 1
    result = results[0]
    assert result.error == "authentication failed using provided and default keys"
    assert result.data is None
    assert result.key_type is None


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
