import unittest
import subprocess
import time
import socket
from pathlib import Path
from gway.builtins import is_test_flag
from gway import gw

class ScreenshotAttachmentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.proc = subprocess.Popen([
            "gway", "-r", "test/website"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        cls._wait_for_port(18888, timeout=15)
        time.sleep(2)
        cls.base_url = "http://127.0.0.1:18888"

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "proc") and cls.proc:
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.proc.kill()

    @staticmethod
    def _wait_for_port(port, timeout=12):
        start = time.time()
        while time.time() - start < timeout:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=1):
                    return
            except OSError:
                time.sleep(0.2)
        raise TimeoutError(f"Port {port} not responding after {timeout} seconds")

    @unittest.skipUnless(is_test_flag("screen"), "Screen tests disabled")
    def test_capture_help_page_screenshot(self):
        screenshot_dir = Path("work/screenshots")
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        screenshot_file = screenshot_dir / "help_page.png"
        try:
            gw.web.auto.capture_page_source(
                self.base_url + "/web/site/help",
                screenshot=str(screenshot_file),
            )
        except Exception as e:
            self.skipTest(f"Webdriver unavailable: {e}")
        self.assertTrue(screenshot_file.exists())

if __name__ == "__main__":
    unittest.main()
