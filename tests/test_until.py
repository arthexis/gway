import unittest
import os
import tempfile
import threading
import time
from unittest.mock import patch
from gway import gw
import gway.runner as runner

class UntilAbortTests(unittest.TestCase):
    def setUp(self):
        self.orig_threads = list(gw._async_threads)

    def tearDown(self):
        gw._async_threads.clear()
        gw._async_threads.extend(self.orig_threads)

    def _start_dummy_async(self, stop_event):
        def dummy():
            while not stop_event.is_set():
                time.sleep(0.01)
        t = threading.Thread(target=dummy, daemon=True)
        gw._async_threads.append(t)
        t.start()
        return t

    def _trigger_change(self, path, stop_event):
        time.sleep(0.2)
        with open(path, 'w') as f:
            f.write('changed')
        time.sleep(0.1)
        stop_event.set()

    def _trigger_version_changes(self, path, stop_event, versions):
        for ver in versions:
            time.sleep(0.2)
            with open(path, 'w') as f:
                f.write(ver)
        time.sleep(0.1)
        stop_event.set()

    def test_until_returns_on_change(self):
        stop = threading.Event()
        dummy = self._start_dummy_async(stop)
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            path = tmp.name
        trig = threading.Thread(target=self._trigger_change, args=(path, stop), daemon=True)
        trig.start()
        orig_watch = runner.watch_file
        def fast_watch(*a, **k):
            k['interval'] = 0.05
            return orig_watch(*a, **k)

        with patch('gway.runner.watch_file', side_effect=fast_watch):
            with patch.object(gw, 'abort') as abort_fn:
                gw.until(file=path)
                abort_fn.assert_not_called()
        dummy.join(1)
        trig.join(1)
        os.unlink(path)
        # If we reach here, until returned without aborting

    def test_until_abort_raises(self):
        stop = threading.Event()
        dummy = self._start_dummy_async(stop)
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            path = tmp.name
        trig = threading.Thread(target=self._trigger_change, args=(path, stop), daemon=True)
        trig.start()
        orig_watch = runner.watch_file
        def fast_watch(*a, **k):
            k['interval'] = 0.05
            return orig_watch(*a, **k)

        with patch('gway.runner.watch_file', side_effect=fast_watch):
            with patch.object(gw, 'abort', side_effect=SystemExit(1)) as abort_fn:
                with self.assertRaises(SystemExit):
                    gw.until(file=path, abort=True)
                abort_fn.assert_called_once()
        dummy.join(1)
        trig.join(1)
        os.unlink(path)

    def test_until_minor_version_change(self):
        stop = threading.Event()
        dummy = self._start_dummy_async(stop)
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            path = tmp.name
            tmp.write(b"1.0.0")
            tmp.flush()
        trig = threading.Thread(
            target=self._trigger_version_changes,
            args=(path, stop, ["1.0.1", "1.1.0"]),
            daemon=True,
        )
        trig.start()
        orig_watch = runner.watch_version
        def fast_watch(*a, **k):
            k['interval'] = 0.05
            return orig_watch(*a, **k)
        with patch('gway.runner.watch_version', side_effect=fast_watch), \
             patch('gway.gw.resource', return_value=path), \
             patch.object(gw, 'abort') as abort_fn:
            gw.until(version=True, minor=True)
            abort_fn.assert_not_called()
        dummy.join(1)
        trig.join(1)
        os.unlink(path)

    def test_until_major_version_change(self):
        stop = threading.Event()
        dummy = self._start_dummy_async(stop)
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            path = tmp.name
            tmp.write(b"1.0.0")
            tmp.flush()
        trig = threading.Thread(
            target=self._trigger_version_changes,
            args=(path, stop, ["1.0.1", "2.0.0"]),
            daemon=True,
        )
        trig.start()
        orig_watch = runner.watch_version
        def fast_watch(*a, **k):
            k['interval'] = 0.05
            return orig_watch(*a, **k)
        with patch('gway.runner.watch_version', side_effect=fast_watch), \
             patch('gway.gw.resource', return_value=path), \
             patch.object(gw, 'abort') as abort_fn:
            gw.until(version=True, major=True)
            abort_fn.assert_not_called()
        dummy.join(1)
        trig.join(1)
        os.unlink(path)

    def test_until_waits_for_future_threads(self):
        """until should keep running even if threads start later."""
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            path = tmp.name

        orig_watch = runner.watch_file

        def fast_watch(*a, **k):
            k['interval'] = 0.05
            return orig_watch(*a, **k)

        started = threading.Event()

        def run_until():
            started.set()
            gw.until(file=path)

        with patch('gway.runner.watch_file', side_effect=fast_watch):
            t = threading.Thread(target=run_until, daemon=True)
            t.start()
            started.wait()
            time.sleep(0.2)
            self.assertTrue(t.is_alive(), 'until exited prematurely')

            stop = threading.Event()
            dummy = self._start_dummy_async(stop)
            with open(path, 'w') as f:
                f.write('changed')
            time.sleep(0.1)
            stop.set()
            t.join(1)
            dummy.join(1)

        os.unlink(path)

if __name__ == '__main__':
    unittest.main()
