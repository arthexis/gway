import unittest
import datetime
from unittest.mock import patch
import sys


class FormatFreshTests(unittest.TestCase):
    @staticmethod
    def _load_webapp():
        import importlib.util
        from pathlib import Path

        app_path = Path(__file__).resolve().parents[1] / "projects" / "web" / "app.py"
        spec = importlib.util.spec_from_file_location("webapp", app_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module


    @classmethod
    def setUpClass(cls):
        cls.webapp = cls._load_webapp()

    def setUp(self):
        # reset cache used by _refresh_fresh_date in case other tests ran
        self.webapp._fresh_mtime = None
        self.webapp._fresh_dt = None

    def test_format_fresh_various_ranges(self):
        base = datetime.datetime(2024, 8, 20, 12, 0, 0)

        class FixedDateTime(datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                return base if tz is None else base.astimezone(tz)

        with patch('webapp.datetime.datetime', FixedDateTime):
            # Seconds
            dt = base - datetime.timedelta(seconds=20)
            self.assertEqual(self.webapp._format_fresh(dt), 'seconds ago')
            # Minutes
            dt = base - datetime.timedelta(minutes=1)
            self.assertEqual(self.webapp._format_fresh(dt), 'a minute ago')
            dt = base - datetime.timedelta(minutes=5)
            self.assertEqual(self.webapp._format_fresh(dt), '5 minutes ago')
            # Hours
            dt = base - datetime.timedelta(hours=1)
            self.assertEqual(self.webapp._format_fresh(dt), 'an hour ago')
            dt = base - datetime.timedelta(hours=3)
            self.assertEqual(self.webapp._format_fresh(dt), '3 hours ago')
            # Days
            dt = base - datetime.timedelta(days=1)
            self.assertEqual(self.webapp._format_fresh(dt), 'a day ago')
            dt = base - datetime.timedelta(days=3)
            self.assertEqual(self.webapp._format_fresh(dt), '3 days ago')
            # Same year
            dt = base - datetime.timedelta(days=30)
            self.assertEqual(self.webapp._format_fresh(dt), 'July 21')
            # Previous year
            dt = base - datetime.timedelta(days=400)
            self.assertEqual(self.webapp._format_fresh(dt), 'July 17, 2023')


class RefreshFreshDateTests(unittest.TestCase):
    @staticmethod
    def _load_webapp():
        import importlib.util
        from pathlib import Path

        app_path = Path(__file__).resolve().parents[1] / "projects" / "web" / "app.py"
        spec = importlib.util.spec_from_file_location("webapp", app_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    @classmethod
    def setUpClass(cls):
        cls.webapp = cls._load_webapp()

    def setUp(self):
        self.webapp._fresh_mtime = None
        self.webapp._fresh_dt = None

    def test_refresh_fresh_date_caching_and_updates(self):
        with patch('webapp.gw.resource', return_value='/fake/VERSION') as res, \
             patch('webapp.os.path.getmtime', side_effect=[100, 100, 200]):
            dt1 = self.webapp._refresh_fresh_date()
            dt2 = self.webapp._refresh_fresh_date()
            dt3 = self.webapp._refresh_fresh_date()

            self.assertEqual(dt1, datetime.datetime.fromtimestamp(100))
            self.assertIs(dt1, dt2)
            self.assertEqual(dt3, datetime.datetime.fromtimestamp(200))
            self.assertNotEqual(dt2, dt3)
            self.assertEqual(res.call_count, 3)

    def test_refresh_fresh_date_errors_return_none(self):
        with patch('webapp.gw.resource', side_effect=Exception('boom')):
            self.assertIsNone(self.webapp._refresh_fresh_date())


class RefreshBuildDateTests(unittest.TestCase):
    @staticmethod
    def _load_webapp():
        import importlib.util
        from pathlib import Path

        app_path = Path(__file__).resolve().parents[1] / "projects" / "web" / "app.py"
        spec = importlib.util.spec_from_file_location("webapp", app_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module

    @classmethod
    def setUpClass(cls):
        cls.webapp = cls._load_webapp()

    def setUp(self):
        self.webapp._build_mtime = None
        self.webapp._build_dt = None

    def test_refresh_build_date_caching_and_updates(self):
        with patch('webapp.gw.resource', return_value='/fake/BUILD') as res, \
             patch('webapp.os.path.getmtime', side_effect=[100, 100, 200]):
            dt1 = self.webapp._refresh_build_date()
            dt2 = self.webapp._refresh_build_date()
            dt3 = self.webapp._refresh_build_date()

            self.assertEqual(dt1, datetime.datetime.fromtimestamp(100))
            self.assertIs(dt1, dt2)
            self.assertEqual(dt3, datetime.datetime.fromtimestamp(200))
            self.assertNotEqual(dt2, dt3)
            self.assertEqual(res.call_count, 3)

    def test_refresh_build_date_errors_return_none(self):
        with patch('webapp.gw.resource', side_effect=Exception('boom')):
            self.assertIsNone(self.webapp._refresh_build_date())


if __name__ == '__main__':
    unittest.main()
