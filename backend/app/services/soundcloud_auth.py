"""
SoundCloud browser-based authentication service.

Since SoundCloud's developer portal is private (no new OAuth app registrations),
we authenticate via Playwright browser automation:
  1. Navigate to SoundCloud login page
  2. Enter email + password
  3. Capture the OAuth token from cookies / local storage / network requests
  4. Persist session (cookies + storage state) to disk per account
  5. Use the captured token for API calls (/me, /tracks, etc.)
  6. Health checks validate the token; re-login if expired
"""

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from typing import Optional, Tuple

from app.services.browser_session import BrowserSessionManager

logger = logging.getLogger(__name__)

SC_LOGIN_URL = "https://soundcloud.com/signin"
SC_API_BASE = "https://api-v2.soundcloud.com"


class SoundCloudAuthService:
    """Handles Playwright-based login and token extraction for SoundCloud."""

    def __init__(self, account_id: str, proxy: Optional[dict] = None):
        self.account_id = account_id
        self.proxy = proxy
        self._browser_mgr = BrowserSessionManager(account_id, proxy=proxy)

    async def login(self, email: str, password: str) -> dict:
        """
        Log into SoundCloud with email/password via Playwright.
        Returns dict with:
          - oauth_token: the captured access token
          - client_id: the public client_id from SoundCloud's JS bundle
          - profile: user profile data (username, avatar, followers, etc.)
          - cookies: serialized cookies for storage
        """
        captured_token = None
        captured_client_id = None

        async with self._browser_mgr.page() as page:
            # ── Intercept network requests to capture the OAuth token ─────────
            async def handle_response(response):
                nonlocal captured_token, captured_client_id
                url = response.url
                try:
                    if "api-v2.soundcloud.com" in url or "api.soundcloud.com" in url:
                        req = response.request
                        auth_header = req.headers.get("authorization", "")
                        if auth_header.startswith("OAuth "):
                            captured_token = auth_header.replace("OAuth ", "")

                    if "client_id=" in url:
                        match = re.search(r"client_id=([a-zA-Z0-9]+)", url)
                        if match:
                            captured_client_id = match.group(1)

                    if "/oauth/token" in url or "/oauth2/token" in url:
                        if response.status == 200:
                            body = await response.json()
                            if "access_token" in body:
                                captured_token = body["access_token"]
                except Exception:
                    pass

            page.on("response", handle_response)

            # ── Navigate to login page ────────────────────────────────────────
            await page.goto(SC_LOGIN_URL, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)

            # ── Handle cookie consent if present ──────────────────────────────
            try:
                accept_btn = page.locator("button#onetrust-accept-btn-handler")
                if await accept_btn.count() > 0:
                    await accept_btn.click()
                    await asyncio.sleep(1)
            except Exception:
                pass

            # ── Click "Sign in" / switch to email login if needed ─────────────
            try:
                email_signin_btn = page.locator(
                    'button:has-text("Continue with email"), '
                    'button:has-text("Sign in"), '
                    'button:has-text("email"), '
                    'a:has-text("Sign in")'
                )
                if await email_signin_btn.count() > 0:
                    await email_signin_btn.first.click()
                    await asyncio.sleep(2)
            except Exception:
                pass

            # ── Fill in email ─────────────────────────────────────────────────
            email_input = page.locator(
                'input[type="email"], '
                'input[name="email"], '
                'input[name="username"], '
                'input[placeholder*="email" i], '
                'input[placeholder*="Email" i]'
            )
            await email_input.first.fill(email)
            await asyncio.sleep(0.5)

            # ── Fill in password ──────────────────────────────────────────────
            password_input = page.locator(
                'input[type="password"], '
                'input[name="password"]'
            )
            await password_input.first.fill(password)
            await asyncio.sleep(0.5)

            # ── Submit login ──────────────────────────────────────────────────
            submit_btn = page.locator(
                'button[type="submit"], '
                'button:has-text("Sign in"), '
                'button:has-text("Log in"), '
                'button:has-text("Continue")'
            )
            await submit_btn.first.click()

            # ── Wait for navigation to complete ────────────────────────────────
            try:
                await page.wait_for_url(
                    lambda url: "soundcloud.com" in url and "/signin" not in url,
                    timeout=15000,
                )
            except Exception:
                error_el = page.locator(
                    '.errorMessage, .sc-form-error, '
                    '[role="alert"], .loginError'
                )
                if await error_el.count() > 0:
                    error_text = await error_el.first.text_content()
                    raise Exception(f"Login failed: {error_text}")
                raise Exception("Login failed: timed out waiting for redirect")

            await asyncio.sleep(3)

            # ── If we didn't capture the token from network, try other methods ──
            if not captured_token:
                captured_token = await page.evaluate("""
                    () => {
                        const keys = Object.keys(localStorage);
                        for (const key of keys) {
                            const val = localStorage.getItem(key);
                            if (val && val.length > 20 && val.length < 200) {
                                if (key.toLowerCase().includes('token') ||
                                    key.toLowerCase().includes('oauth') ||
                                    key.toLowerCase().includes('access')) {
                                    return val;
                                }
                            }
                        }
                        const cookies = document.cookie.split(';');
                        for (const c of cookies) {
                            const [name, value] = c.trim().split('=');
                            if (name === 'oauth_token' || name === 'sc_anonymous_id') {
                                return value;
                            }
                        }
                        return null;
                    }
                """)

            if not captured_token:
                await page.goto("https://soundcloud.com/you/library", wait_until="networkidle")
                await asyncio.sleep(3)

            if not captured_token:
                captured_token = await page.evaluate("""
                    () => {
                        if (window.__sc_hydration) {
                            for (const item of window.__sc_hydration) {
                                if (item.hydratable === 'user' && item.data?.oauth_token) {
                                    return item.data.oauth_token;
                                }
                            }
                        }
                        if (window.sc && window.sc.accessToken) return window.sc.accessToken;
                        return null;
                    }
                """)

            # ── Capture client_id if we didn't get it ─────────────────────────
            if not captured_client_id:
                captured_client_id = await page.evaluate("""
                    () => {
                        const scripts = document.querySelectorAll('script[src]');
                        for (const s of scripts) {
                            if (s.src.includes('client_id=')) {
                                const match = s.src.match(/client_id=([a-zA-Z0-9]+)/);
                                if (match) return match[1];
                            }
                        }
                        if (window.__sc_hydration) {
                            for (const item of window.__sc_hydration) {
                                if (item.data?.client_id) return item.data.client_id;
                            }
                        }
                        return null;
                    }
                """)

            # ── Get profile data ──────────────────────────────────────────────
            profile = None
            if captured_token:
                try:
                    profile = await self._fetch_profile(page, captured_token, captured_client_id)
                except Exception as e:
                    logger.warning(f"Profile fetch failed: {e}")

            if not profile:
                profile = await self._scrape_profile(page)

            # ── Save session ──────────────────────────────────────────────────
            await self._browser_mgr.save_session()

            # ── Get all cookies for storage ───────────────────────────────────
            context = await self._browser_mgr._get_context()
            cookies = await context.cookies()

        result = {
            "oauth_token": captured_token,
            "client_id": captured_client_id,
            "profile": profile,
            "cookies": json.dumps(cookies),
            "logged_in": True,
            "login_time": datetime.now(timezone.utc).isoformat(),
        }

        if not captured_token:
            logger.warning(
                f"Logged in but couldn't capture OAuth token for {self.account_id}. "
                "Browser session is saved — engagement actions will still work via Playwright."
            )
            result["logged_in"] = True
            result["note"] = "session_only"

        return result

    async def _fetch_profile(self, page, token: str, client_id: str = None) -> dict:
        """Fetch profile data from SC API using captured token."""
        import httpx

        headers = {"Authorization": f"OAuth {token}"}
        params = {}
        if client_id:
            params["client_id"] = client_id

        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{SC_API_BASE}/me", headers=headers, params=params)
            if r.status_code == 200:
                data = r.json()
                return {
                    "platform_user_id": str(data.get("id", "")),
                    "username": data.get("permalink", data.get("username", "")),
                    "display_name": data.get("full_name", data.get("username", "")),
                    "avatar_url": data.get("avatar_url", ""),
                    "bio": data.get("description", ""),
                    "follower_count": data.get("followers_count", 0),
                    "following_count": data.get("followings_count", 0),
                    "track_count": data.get("track_count", 0),
                    "likes_count": data.get("public_favorites_count", 0),
                    "city": data.get("city", ""),
                    "country": data.get("country_code", ""),
                    "profile_url": data.get("permalink_url", ""),
                    "is_verified": data.get("verified", False),
                }
        return None

    async def _scrape_profile(self, page) -> dict:
        """Fallback: scrape profile data from the SoundCloud page."""
        try:
            await page.goto("https://soundcloud.com/you", wait_until="networkidle", timeout=15000)
            await asyncio.sleep(2)

            profile = await page.evaluate("""
                () => {
                    const data = {};
                    if (window.__sc_hydration) {
                        for (const item of window.__sc_hydration) {
                            if (item.hydratable === 'user') {
                                const u = item.data;
                                return {
                                    platform_user_id: String(u.id || ''),
                                    username: u.permalink || u.username || '',
                                    display_name: u.full_name || u.username || '',
                                    avatar_url: u.avatar_url || '',
                                    bio: u.description || '',
                                    follower_count: u.followers_count || 0,
                                    following_count: u.followings_count || 0,
                                    track_count: u.track_count || 0,
                                    likes_count: u.public_favorites_count || 0,
                                    profile_url: u.permalink_url || '',
                                    is_verified: u.verified || false,
                                };
                            }
                        }
                    }
                    const name = document.querySelector('.profileHeaderInfo__userName')?.textContent?.trim();
                    const avatar = document.querySelector('.profileHeaderInfo__avatar img')?.src;
                    return {
                        username: name || '',
                        display_name: name || '',
                        avatar_url: avatar || '',
                    };
                }
            """)
            return profile
        except Exception as e:
            logger.warning(f"Profile scrape failed: {e}")
            return {}

    async def validate_session(self) -> dict:
        """
        Check if the stored session is still valid.
        Returns: {"valid": bool, "profile": dict|None, "needs_relogin": bool}
        """
        try:
            async with self._browser_mgr.page() as page:
                await page.goto(
                    "https://soundcloud.com/you/library",
                    wait_until="networkidle",
                    timeout=15000,
                )
                await asyncio.sleep(2)

                current_url = page.url
                if "/signin" in current_url or "/login" in current_url:
                    return {"valid": False, "needs_relogin": True}

                profile = await page.evaluate("""
                    () => {
                        if (window.__sc_hydration) {
                            for (const item of window.__sc_hydration) {
                                if (item.hydratable === 'user') {
                                    const u = item.data;
                                    return {
                                        platform_user_id: String(u.id || ''),
                                        username: u.permalink || '',
                                        display_name: u.full_name || '',
                                        avatar_url: u.avatar_url || '',
                                        follower_count: u.followers_count || 0,
                                        following_count: u.followings_count || 0,
                                        track_count: u.track_count || 0,
                                    };
                                }
                            }
                        }
                        return null;
                    }
                """)

                await self._browser_mgr.save_session()
                return {"valid": True, "profile": profile, "needs_relogin": False}

        except Exception as e:
            logger.error(f"Session validation failed for {self.account_id}: {e}")
            return {"valid": False, "needs_relogin": True, "error": str(e)}

    async def relogin(self, email: str, password: str) -> dict:
        """Clear the old session and log in fresh."""
        await self._browser_mgr.clear_session()
        return await self.login(email, password)

    async def close(self):
        await self._browser_mgr.close()
