"""Utility helpers for automated website testing using Selenium."""

from __future__ import annotations

from contextlib import contextmanager
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.firefox.service import Service as FirefoxService
from webdriver_manager.firefox import GeckoDriverManager

DEFAULT_BROWSER = "chrome"


def get_driver(*, browser: str = DEFAULT_BROWSER, headless: bool = True):
    """Return a Selenium WebDriver instance for the selected browser."""
    browser = browser.lower()
    if browser == "chrome":
        options = ChromeOptions()
        if headless:
            options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        service = ChromeService(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=options)
    elif browser == "firefox":
        options = FirefoxOptions()
        if headless:
            options.add_argument("--headless")
        service = FirefoxService(GeckoDriverManager().install())
        return webdriver.Firefox(service=service, options=options)
    else:
        raise ValueError(f"Unsupported browser: {browser}")


@contextmanager
def browser(*, url: str | None = None, browser: str = DEFAULT_BROWSER, headless: bool = True):
    """Yield a WebDriver instance and ensure it quits on exit."""
    drv = get_driver(browser=browser, headless=headless)
    if url:
        drv.get(url)
    try:
        yield drv
    finally:
        drv.quit()


def capture_page_source(
    url: str,
    *,
    browser: str = DEFAULT_BROWSER,
    headless: bool = True,
    wait: float = 2.0,
    screenshot: str | None = None,
) -> str:
    """Return page source for ``url``. Optionally save a screenshot."""
    import time

    with browser(url=url, browser=browser, headless=headless) as drv:
        if wait:
            time.sleep(wait)
        if screenshot:
            drv.save_screenshot(screenshot)
        return drv.page_source
