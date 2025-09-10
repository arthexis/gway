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
