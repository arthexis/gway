import datetime
import sys
import tempfile
import types
import unittest
import unittest.mock
from contextlib import contextmanager
from pathlib import Path
from gway import gw
from gway.builtins import is_test_flag


@unittest.skipUnless(
    is_test_flag("lcd"),
    "LCD tests disabled (enable with --flags lcd)",
)
class LCDTests(unittest.TestCase):
    @contextmanager
    def _mock_backlight(self, initial_state: str):
        writes: list[tuple[int, int]] = []

        class FakeSMBus:
            def __init__(self, bus_no):
                self.bus_no = bus_no

            def write_byte(self, addr, value):
                writes.append((addr, value))

        fake_mod = types.SimpleNamespace(SMBus=FakeSMBus)
        lcd_mod = sys.modules[gw.lcd.show.__module__]
        original_mask = lcd_mod._backlight_mask
        original_resource = gw.resource

        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "lcd-backlight.txt"
            state_path.write_text(initial_state)

            def fake_resource(*parts, **kwargs):
                joined = "/".join(str(p) for p in parts)
                normalized = joined.replace("\\", "/")
                if normalized == "work/lcd-backlight.txt":
                    if kwargs.get("touch") and not state_path.exists():
                        state_path.touch()
                    return state_path
                return original_resource(*parts, **kwargs)

            with unittest.mock.patch.dict("sys.modules", {"smbus": fake_mod}), \
                 unittest.mock.patch.object(gw, "resource", side_effect=fake_resource):
                state_value = initial_state.strip().lower()
                lcd_mod._backlight_mask = (
                    lcd_mod.LCD_BACKLIGHT
                    if state_value not in {"0", "off", "false", "no"}
                    else 0
                )
                try:
                    yield writes, lcd_mod, state_path
                finally:
                    lcd_mod._backlight_mask = original_mask
    def test_show_writes_to_i2c_bus(self):
        writes = []
        buses = []

        class FakeSMBus:
            def __init__(self, bus_no):
                buses.append(bus_no)
            def write_byte(self, addr, value):
                writes.append((addr, value))

        fake_mod = types.SimpleNamespace(SMBus=FakeSMBus)
        with unittest.mock.patch.dict("sys.modules", {"smbus": fake_mod}):
            gw.lcd.show("Hi")

        self.assertEqual(buses, [1])
        self.assertGreater(len(writes), 0)
        self.assertTrue(all(addr == 0x27 for addr, _ in writes))

    def test_brightness_toggles_backlight(self):
        writes = []

        class FakeSMBus:
            def __init__(self, bus_no):
                self.bus_no = bus_no

            def write_byte(self, addr, value):
                writes.append((addr, value))

        fake_mod = types.SimpleNamespace(SMBus=FakeSMBus)
        lcd_mod = sys.modules[gw.lcd.show.__module__]
        original_mask = lcd_mod._backlight_mask
        try:
            with unittest.mock.patch.dict("sys.modules", {"smbus": fake_mod}):
                gw.lcd.brightness(0)
                gw.lcd.brightness("on")
        finally:
            lcd_mod._backlight_mask = original_mask

        self.assertEqual(writes, [(0x27, 0), (0x27, lcd_mod.LCD_BACKLIGHT)])
        self.assertEqual(lcd_mod._backlight_mask, lcd_mod.LCD_BACKLIGHT)

    def test_brightness_invalid_value_raises(self):
        lcd_mod = sys.modules[gw.lcd.show.__module__]
        original_mask = lcd_mod._backlight_mask
        try:
            with self.assertRaises(ValueError):
                gw.lcd.brightness("full")
        finally:
            lcd_mod._backlight_mask = original_mask

    def test_light_toggles_backlight(self):
        with self._mock_backlight("on") as (writes, lcd_mod, state_path):
            result = gw.lcd.light()
            saved = state_path.read_text().strip()
            writes_copy = list(writes)
            mask_after = lcd_mod._backlight_mask

        self.assertEqual(result, {"backlight": "off"})
        self.assertEqual(saved, "off")
        self.assertEqual(writes_copy, [(0x27, 0)])
        self.assertEqual(mask_after, 0)

    def test_light_on_flag_sets_backlight_on(self):
        with self._mock_backlight("off") as (writes, lcd_mod, state_path):
            result = gw.lcd.light(on=True)
            saved = state_path.read_text().strip()
            writes_copy = list(writes)
            mask_after = lcd_mod._backlight_mask
            expected_mask = lcd_mod.LCD_BACKLIGHT

        self.assertEqual(result, {"backlight": "on"})
        self.assertEqual(saved, "on")
        self.assertEqual(writes_copy, [(0x27, expected_mask)])
        self.assertEqual(mask_after, expected_mask)

    def test_light_off_flag_sets_backlight_off(self):
        with self._mock_backlight("on") as (writes, lcd_mod, state_path):
            result = gw.lcd.light(off=True)
            saved = state_path.read_text().strip()
            writes_copy = list(writes)
            mask_after = lcd_mod._backlight_mask

        self.assertEqual(result, {"backlight": "off"})
        self.assertEqual(saved, "off")
        self.assertEqual(writes_copy, [(0x27, 0)])
        self.assertEqual(mask_after, 0)

    def test_light_conflicting_flags_raise(self):
        with self.assertRaises(ValueError):
            gw.lcd.light(on=True, off=True)

    def test_scroll_option_scrolls_message(self):
        class FakeSMBus:
            def __init__(self, bus_no):
                pass

            def write_byte(self, addr, value):
                pass

        fake_mod = types.SimpleNamespace(SMBus=FakeSMBus)
        lcd_mod = sys.modules[gw.lcd.show.__module__]
        with unittest.mock.patch.dict("sys.modules", {"smbus": fake_mod}), \
             unittest.mock.patch.object(lcd_mod, "_lcd_string") as lcd_str, \
             unittest.mock.patch.object(lcd_mod.time, "sleep") as sleep:
            gw.lcd.show("Scrolling", scroll=0.1)

        self.assertGreater(lcd_str.call_count, 1)
        delays = [call.args[0] for call in sleep.call_args_list]
        self.assertTrue(any(abs(d - 0.1) < 1e-6 for d in delays))

    def test_ratio_option_adjusts_row_speeds(self):
        class FakeSMBus:
            def __init__(self, bus_no):
                pass

            def write_byte(self, addr, value):
                pass

        fake_mod = types.SimpleNamespace(SMBus=FakeSMBus)
        lcd_mod = sys.modules[gw.lcd.show.__module__]
        with unittest.mock.patch.dict("sys.modules", {"smbus": fake_mod}), \
             unittest.mock.patch.object(lcd_mod, "_lcd_string") as lcd_str, \
             unittest.mock.patch.object(lcd_mod.time, "sleep"):
            gw.lcd.show("Scroll", scroll=0.1, ratio=2)

        top_calls = [c for c in lcd_str.call_args_list if c.args[3] == lcd_mod.LCD_LINE_1]
        bottom_calls = [c for c in lcd_str.call_args_list if c.args[3] == lcd_mod.LCD_LINE_2]
        self.assertAlmostEqual(len(bottom_calls) / len(top_calls), 4, delta=0.1)

    def test_hold_reverts_to_previous_message(self):
        class FakeSMBus:
            def __init__(self, bus_no):
                pass

            def write_byte(self, addr, value):
                pass

        fake_mod = types.SimpleNamespace(SMBus=FakeSMBus)
        lcd_mod = sys.modules[gw.lcd.show.__module__]
        with tempfile.TemporaryDirectory() as tmpdir:
            last_path = Path(tmpdir) / "last.txt"
            last_path.write_text("Prev")
            with unittest.mock.patch.dict("sys.modules", {"smbus": fake_mod}), \
                 unittest.mock.patch.object(gw, "resource", return_value=last_path), \
                 unittest.mock.patch.object(lcd_mod, "_lcd_string") as lcd_str, \
                 unittest.mock.patch.object(lcd_mod.time, "sleep") as sleep:
                gw.lcd.show("New", hold=1)

            self.assertEqual(last_path.read_text(), "Prev")
            messages = [call.args[2].strip() for call in lcd_str.call_args_list]
            delays = [call.args[0] for call in sleep.call_args_list]

        self.assertIn("New", messages)
        self.assertIn("Prev", messages)
        self.assertTrue(any(abs(d - 1) < 1e-6 for d in delays))

    def test_wrap_option_wraps_text(self):
        class FakeSMBus:
            def __init__(self, bus_no):
                pass

            def write_byte(self, addr, value):
                pass

        fake_mod = types.SimpleNamespace(SMBus=FakeSMBus)
        lcd_mod = sys.modules[gw.lcd.show.__module__]
        message = "X" * 20
        with unittest.mock.patch.dict("sys.modules", {"smbus": fake_mod}), \
             unittest.mock.patch.object(lcd_mod, "_lcd_string") as lcd_str:
            gw.lcd.show(message, wrap=True)

        line1 = lcd_str.call_args_list[0].args[2]
        line2 = lcd_str.call_args_list[1].args[2]
        self.assertEqual(line1.strip(), "X" * 16)
        self.assertEqual(line2.strip(), "X" * 4)

    def test_scroll_and_wrap_snakes_text(self):
        class FakeSMBus:
            def __init__(self, bus_no):
                pass

            def write_byte(self, addr, value):
                pass

        fake_mod = types.SimpleNamespace(SMBus=FakeSMBus)
        lcd_mod = sys.modules[gw.lcd.show.__module__]
        message = "ABCDEFG"
        with unittest.mock.patch.dict("sys.modules", {"smbus": fake_mod}), \
             unittest.mock.patch.object(lcd_mod, "_lcd_string") as lcd_str, \
             unittest.mock.patch.object(lcd_mod.time, "sleep"):
            gw.lcd.show(message, scroll=0.1, wrap=True)

        calls = lcd_str.call_args_list
        pairs = [
            (calls[i].args[2], calls[i + 1].args[2])
            for i in range(0, len(calls), 2)
        ]
        first_top, first_bottom = next((p for p in pairs if p[0].strip()), ("", ""))
        self.assertEqual(first_top, " " * 15 + "A")
        self.assertTrue(first_bottom.startswith("B"))

    def test_show_resolves_sigils(self):
        class FakeSMBus:
            def __init__(self, bus_no):
                pass

            def write_byte(self, addr, value):
                pass

        fake_mod = types.SimpleNamespace(SMBus=FakeSMBus)
        lcd_mod = sys.modules[gw.lcd.show.__module__]
        gw.context["LCD_MSG"] = "World"
        try:
            with unittest.mock.patch.dict("sys.modules", {"smbus": fake_mod}), \
                 unittest.mock.patch.object(lcd_mod, "_lcd_string") as lcd_str:
                gw.lcd.show("Hello [LCD_MSG]")
        finally:
            gw.context.pop("LCD_MSG", None)

        msg = lcd_str.call_args_list[0].args[2]
        self.assertEqual(msg.strip(), "Hello World")

    def test_show_handles_missing_smbus_gracefully(self):
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name in {"smbus", "smbus2"}:
                raise ModuleNotFoundError
            return real_import(name, *args, **kwargs)

        with unittest.mock.patch.object(builtins, "__import__", side_effect=fake_import):
            with unittest.mock.patch.object(gw, "error") as err, \
                 unittest.mock.patch("builtins.print") as mock_print:
                gw.lcd.show("Test")

        err.assert_called_once()
        mock_print.assert_called_once()
        self.assertIn("i2c-tools", err.call_args[0][0])

    def test_show_falls_back_to_smbus2(self):
        import builtins

        writes = []

        class FakeSMBus2:
            def __init__(self, bus_no):
                writes.append(bus_no)

            def write_byte(self, addr, value):
                pass

        fake_mod = types.SimpleNamespace(SMBus=FakeSMBus2)

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "smbus":
                raise ModuleNotFoundError
            return real_import(name, *args, **kwargs)

        with unittest.mock.patch.dict(sys.modules, {"smbus2": fake_mod}):
            with unittest.mock.patch.object(builtins, "__import__", side_effect=fake_import):
                gw.lcd.show("Hi")

        self.assertEqual(writes, [1])

    def test_boot_function_removed(self):
        self.assertFalse(hasattr(gw.lcd, "boot"))

    def test_clock_displays_iso_date_and_time(self):
        class FakeSMBus:
            def __init__(self, bus_no):
                self.bus_no = bus_no

            def write_byte(self, addr, value):
                pass

        fake_mod = types.SimpleNamespace(SMBus=FakeSMBus)
        lcd_mod = sys.modules[gw.lcd.show.__module__]
        fixed = datetime.datetime(2024, 1, 2, 3, 4, 5)
        with unittest.mock.patch.dict("sys.modules", {"smbus": fake_mod}), \
             unittest.mock.patch.object(lcd_mod, "_lcd_string") as lcd_str, \
             unittest.mock.patch.object(lcd_mod.time, "sleep") as sleep, \
             unittest.mock.patch.object(lcd_mod.datetime, "datetime") as dt_cls:
            dt_cls.now.return_value = fixed
            gw.lcd.clock(updates=1)

        self.assertEqual(dt_cls.now.call_args.kwargs, {})
        self.assertGreaterEqual(lcd_str.call_count, 2)
        top_call = lcd_str.call_args_list[0]
        bottom_call = lcd_str.call_args_list[1]
        self.assertEqual(top_call.args[3], lcd_mod.LCD_LINE_1)
        self.assertEqual(bottom_call.args[3], lcd_mod.LCD_LINE_2)
        self.assertEqual(top_call.args[2].strip(), "Tue 2024-01-02")
        self.assertEqual(bottom_call.args[2].strip(), "03:04:05")
        intervals = [call.args[0] for call in sleep.call_args_list if call.args]
        self.assertNotIn(1.0, intervals)

    def test_clock_honours_timezone_string(self):
        class FakeSMBus:
            def __init__(self, bus_no):
                self.bus_no = bus_no

            def write_byte(self, addr, value):
                pass

        fake_mod = types.SimpleNamespace(SMBus=FakeSMBus)
        lcd_mod = sys.modules[gw.lcd.show.__module__]
        fixed = datetime.datetime(2024, 1, 2, 3, 4, 5, tzinfo=datetime.timezone.utc)
        with unittest.mock.patch.dict("sys.modules", {"smbus": fake_mod}), \
             unittest.mock.patch.object(lcd_mod, "_lcd_string") as lcd_str, \
             unittest.mock.patch.object(lcd_mod.time, "sleep") as sleep, \
             unittest.mock.patch.object(lcd_mod.datetime, "datetime") as dt_cls:
            dt_cls.now.return_value = fixed
            gw.lcd.clock(tz="UTC", updates=1)

        self.assertEqual(dt_cls.now.call_args.kwargs, {"tz": datetime.timezone.utc})
        self.assertGreaterEqual(lcd_str.call_count, 2)
        top_call = lcd_str.call_args_list[0]
        bottom_call = lcd_str.call_args_list[1]
        self.assertEqual(top_call.args[2].strip(), "Tue 2024-01-02")
        self.assertEqual(bottom_call.args[2].strip(), "03:04:05")
        intervals = [call.args[0] for call in sleep.call_args_list if call.args]
        self.assertNotIn(1.0, intervals)
