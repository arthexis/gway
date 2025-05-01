import unittest
import tempfile
import os
import time
import threading

from gway import Gateway


class TestGwayIntegration(unittest.TestCase):
    def setUp(self):
        
        self.gw = Gateway()
        self.lockfile = tempfile.NamedTemporaryFile(delete=False)
        self.lockfile.close()

    def tearDown(self):
        try:
            os.remove(self.lockfile.name)
        except FileNotFoundError:
            pass

    def test_async_server_starts_and_exits_on_lockfile_change(self):
        # Call real async function from GWAY
        result = self.gw.website.start_server(daemon=True)
        self.assertIn("async", result.lower())

        # Let the thread spin up
        time.sleep(1)

        # Run hold in background
        hold_thread = threading.Thread(
            target=self.gw.hold,
            args=(self.lockfile.name,),
            daemon=True
        )
        hold_thread.start()

        # Wait briefly, then simulate lockfile change
        time.sleep(1)
        os.utime(self.lockfile.name, None)

        # Wait for hold to exit
        hold_thread.join(timeout=5)

        self.assertFalse(
            any(t.is_alive() for t in self.gw._async_threads),
            "Some async threads are still alive after lockfile trigger"
        )

    def test_hold_runs_forever_without_lockfile(self):
        # Start real async server
        result = self.gw.website.start_server(daemon=True)
        self.assertIn("async", result.lower())

        # Let the thread start
        time.sleep(1)

        # Run hold in background with no lockfile
        hold_thread = threading.Thread(
            target=self.gw.hold,
            daemon=True
        )
        hold_thread.start()

        time.sleep(2)  # Wait and ensure it's still running

        self.assertTrue(
            hold_thread.is_alive(),
            "Hold thread exited early without lockfile"
        )

        # Clean up (simulate external kill)
        for t in self.gw._async_threads:
            t.join(timeout=2)

        self.gw._async_threads.clear()


if __name__ == "__main__":
    unittest.main()
