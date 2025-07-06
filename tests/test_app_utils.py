import unittest
import datetime
import importlib.util
from pathlib import Path
from unittest.mock import patch

app_path = Path(__file__).resolve().parents[1] / "projects" / "web" / "app.py"
spec = importlib.util.spec_from_file_location("webapp", app_path)
webapp = importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name] = webapp
spec.loader.exec_module(webapp)


class FormatFreshTests(unittest.TestCase):
    def setUp(self):
        # reset cache used by _refresh_fresh_date in case other tests ran
        webapp._fresh_mtime = None
        webapp._fresh_dt = None

    def test_format_fresh_various_ranges(self):
        base = datetime.datetime(2024, 8, 20, 12, 0, 0)

        class FixedDateTime(datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                return base if tz is None else base.astimezone(tz)

        with patch('webapp.datetime.datetime', FixedDateTime):
            # Seconds
            dt = base - datetime.timedelta(seconds=20)
            self.assertEqual(webapp._format_fresh(dt), 'seconds ago')
            # Minutes
            dt = base - datetime.timedelta(minutes=1)
            self.assertEqual(webapp._format_fresh(dt), 'a minute ago')
            dt = base - datetime.timedelta(minutes=5)
            self.assertEqual(webapp._format_fresh(dt), '5 minutes ago')
            # Hours
            dt = base - datetime.timedelta(hours=1)
            self.assertEqual(webapp._format_fresh(dt), 'an hour ago')
            dt = base - datetime.timedelta(hours=3)
            self.assertEqual(webapp._format_fresh(dt), '3 hours ago')
            # Days
            dt = base - datetime.timedelta(days=1)
            self.assertEqual(webapp._format_fresh(dt), 'a day ago')
            dt = base - datetime.timedelta(days=3)
            self.assertEqual(webapp._format_fresh(dt), '3 days ago')
            # Same year
            dt = base - datetime.timedelta(days=30)
            self.assertEqual(webapp._format_fresh(dt), 'July 21')
            # Previous year
            dt = base - datetime.timedelta(days=400)
            self.assertEqual(webapp._format_fresh(dt), 'July 17, 2023')


class RefreshFreshDateTests(unittest.TestCase):
    def setUp(self):
        webapp._fresh_mtime = None
        webapp._fresh_dt = None

    def test_refresh_fresh_date_caching_and_updates(self):
        with patch('webapp.gw.resource', return_value='/fake/VERSION') as res, \
             patch('webapp.os.path.getmtime', side_effect=[100, 100, 200]):
            dt1 = webapp._refresh_fresh_date()
            dt2 = webapp._refresh_fresh_date()
            dt3 = webapp._refresh_fresh_date()

            self.assertEqual(dt1, datetime.datetime.fromtimestamp(100))
            self.assertIs(dt1, dt2)
            self.assertEqual(dt3, datetime.datetime.fromtimestamp(200))
            self.assertNotEqual(dt2, dt3)
            self.assertEqual(res.call_count, 3)

    def test_refresh_fresh_date_errors_return_none(self):
        with patch('webapp.gw.resource', side_effect=Exception('boom')):
            self.assertIsNone(webapp._refresh_fresh_date())


if __name__ == '__main__':
    unittest.main()
