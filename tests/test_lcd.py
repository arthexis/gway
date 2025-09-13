import sys
import unittest
import types
from gway import gw


class LCDTests(unittest.TestCase):
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

    def test_scroll_flag_scrolls_message(self):
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
            gw.lcd.show("Scrolling", scroll=True, ms=100)

        self.assertGreater(lcd_str.call_count, 1)
        delays = [call.args[0] for call in sleep.call_args_list]
        self.assertTrue(any(abs(d - 0.1) < 1e-6 for d in delays))

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
            if name == "smbus":
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
