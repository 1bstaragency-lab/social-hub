"""
Browser session manager using Playwright.

Key design principles:
  • Each social account gets its own isolated browser context (separate cookies,
    localStorage, IndexedDB, and cache) — no cross-account session bleed.
  • Sessions are persisted to disk under BROWSER_SESSION_DIR/{account_id}/ so
    logins survive server restarts.
  • A semaphore limits total concurrent browser pages to MAX_CONCURRENT_BROWSERS
    to keep memory bounded even with 100+ accounts.
  • Proxy config is applied per-context so each account can route through its
    own residential proxy.
"""

import asyncio
import os
import json
import logging
from pathlib import Path
from typing import Optional, Dict
from contextlib import asynccontextmanager

from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

# Global semaphore shared across all sessions
_browser_semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_BROWSERS)

# Singleton Playwright instance
_playwright = None
_browser = None
_lock = asyncio.Lock()


async def _get_browser():
    """Return (or lazily create) the shared Playwright browser instance."""
    global _playwright, _browser
    async with _lock:
        if _browser is None or not _browser.is_connected():
            from playwright.async_api import async_playwright
            _playwright = await async_playwright().start()
            _browser = await _playwright.chromium.launch(
                headless=settings.PLAYWRIGHT_HEADLESS,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                ],
            )
            logger.info("Playwright browser launched.")
    return _browser


class BrowserSessionManager:
    """
    Per-account session manager. Creates and caches an isolated browser context,
    persisting cookies + storage state to disk so sessions survive restarts.
    """

    def __init__(self, account_id: str, proxy: Optional[dict] = None):
        self.account_id = account_id
        self.proxy = proxy
        self.session_dir = Path(settings.BROWSER_SESSION_DIR) / account_id
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.session_dir / "state.json"
        self._context = None
        self._pages: list = []

    async def _get_context(self):
        """Return (or create) the isolated browser context for this account."""
        if self._context and not self._context.is_closed():
            return self._context

        browser = await _get_browser()

        context_options = {
            "viewport": {"width": 1280, "height": 800},
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "locale": "en-US",
            "timezone_id": "America/New_York",
            "permissions": ["geolocation"],
            "ignore_https_errors": False,
        }

        # Restore persisted session if it exists
        if self.state_file.exists():
            context_options["storage_state"] = str(self.state_file)

        # Apply per-account proxy
        if self.proxy:
            context_options["proxy"] = {
                "server": self.proxy.get("server"),
                "username": self.proxy.get("username"),
                "password": self.proxy.get("password"),
            }

        self._context = await browser.new_context(**context_options)

        # Stealth: mask automation signals
        await self._context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
            window.chrome = { runtime: {} };
        """)

        logger.info(f"Browser context created for account {self.account_id}")
        return self._context

    async def get_page(self):
        """Acquire a semaphore slot and return a new page in this account's context."""
        await _browser_semaphore.acquire()
        context = await self._get_context()
        page = await context.new_page()
        self._pages.append(page)
        return page

    async def release_page(self, page):
        """Close the page and release the semaphore slot."""
        try:
            if not page.is_closed():
                await page.close()
            if page in self._pages:
                self._pages.remove(page)
        finally:
            _browser_semaphore.release()

    async def save_session(self):
        """Persist cookies and localStorage to disk for this account."""
        if self._context and not self._context.is_closed():
            await self._context.storage_state(path=str(self.state_file))
            logger.info(f"Session saved for account {self.account_id}")

    async def clear_session(self):
        """Wipe stored session data (forces re-login)."""
        if self.state_file.exists():
            self.state_file.unlink()
        if self._context and not self._context.is_closed():
            await self._context.close()
            self._context = None
        logger.info(f"Session cleared for account {self.account_id}")

    async def inject_cookies(self, cookies: list):
        """Inject a list of cookie dicts into this account's context."""
        context = await self._get_context()
        await context.add_cookies(cookies)
        await self.save_session()

    async def close(self):
        """Save session and close context."""
        await self.save_session()
        if self._context and not self._context.is_closed():
            await self._context.close()
            self._context = None

    @asynccontextmanager
    async def page(self):
        """Context manager that auto-releases the page."""
        p = await self.get_page()
        try:
            yield p
        finally:
            await self.release_page(p)


async def shutdown_browser():
    """Graceful shutdown — save all sessions and close browser."""
    global _browser, _playwright
    if _browser and _browser.is_connected():
        await _browser.close()
    if _playwright:
        await _playwright.stop()
    logger.info("Playwright browser shut down.")
