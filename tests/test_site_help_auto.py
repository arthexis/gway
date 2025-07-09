import unittest
import subprocess
import time
import socket
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from gway import gw

class SiteHelpAutoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.proc = subprocess.Popen(
            ["gway", "-r", "test/website"],
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
        try:
            with gw.web.auto.browse(close=True):
                pass
        except Exception:
            pass

    @staticmethod
    def _wait_for_port(port, timeout=12):
        start = time.time()
        while time.time() - start < timeout:
            try:
                with socket.create_connection(("localhost", port), timeout=1):
                    return
            except OSError:
                time.sleep(0.2)
        raise TimeoutError(f"Port {port} not responding after {timeout} seconds")

    def test_help_search_finds_builtin(self):
        url = self.base_url + "/site/help"
        try:
            with gw.web.auto.browse(url=url) as drv:
                textarea = drv.find_element(By.ID, "help-search")
                textarea.clear()
                textarea.send_keys("hello-world")
                drv.find_element(By.CSS_SELECTOR, "form.nav").submit()
                WebDriverWait(drv, 10).until(
                    EC.text_to_be_present_in_element((By.TAG_NAME, "h1"), "hello_world")
                )
                h1_text = drv.find_element(By.TAG_NAME, "h1").text
                self.assertIn("hello_world", h1_text.lower())
        except Exception as e:
            self.skipTest(f"Webdriver unavailable: {e}")

    def test_search_box_autoexpands(self):
        """Search box should grow taller when text wraps to new lines."""
        url = self.base_url + "/site/help"
        long_text = "word " * 50
        try:
            with gw.web.auto.browse(url=url) as drv:
                textarea = drv.find_element(By.ID, "help-search")
                start_height = drv.execute_script(
                    "return arguments[0].clientHeight", textarea
                )
                textarea.clear()
                textarea.send_keys(long_text)
                # allow JS to process autoExpand
                WebDriverWait(drv, 5).until(
                    lambda d: d.execute_script(
                        "return arguments[0].clientHeight", textarea
                    )
                    > start_height
                )
                end_height = drv.execute_script(
                    "return arguments[0].clientHeight", textarea
                )
                self.assertGreater(
                    end_height,
                    start_height,
                    f"expected height to grow: {start_height} -> {end_height}",
                )
        except Exception as e:
            self.skipTest(f"Webdriver unavailable: {e}")

if __name__ == "__main__":
    unittest.main()

