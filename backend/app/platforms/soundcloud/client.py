"""
SoundCloud client — hybrid approach:
  • Uses the unofficial SoundCloud API (with OAuth token) for reading data.
  • Uses Playwright browser automation for engagement actions
    (like, repost, comment, follow, play) that require a real session.
  • Integrates with SoundCloudAuthService for browser-based login
    and session validation when the developer portal is unavailable.
"""

import asyncio
import random
import logging
from typing import Optional

from app.platforms.base import BasePlatformClient
from app.services.browser_session import BrowserSessionManager
from app.services.soundcloud_auth import SoundCloudAuthService

logger = logging.getLogger(__name__)

SC_API_BASE = "https://api-v2.soundcloud.com"


class SoundCloudClient(BasePlatformClient):
    def __init__(self, account_id: str, credentials: dict, proxy: Optional[dict] = None):
        super().__init__(account_id, credentials, proxy)
        self.oauth_token = credentials.get("access_token")
        self.client_id = credentials.get("client_id", "")
        self._browser_mgr = BrowserSessionManager(account_id, proxy=proxy)
        self._auth_service = SoundCloudAuthService(account_id, proxy=proxy)

    # ── Helpers ──────────────────────────────────────────────────────────────────────

    async def _api_get(self, path: str, params: dict = None) -> dict:
        import httpx

        headers = {"Authorization": f"OAuth {self.oauth_token}"}
        params = params or {}
        if self.client_id:
            params["client_id"] = self.client_id
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"{SC_API_BASE}{path}", headers=headers, params=params
            )
            r.raise_for_status()
            return r.json()

    async def _human_delay(self, min_s: float = 0.8, max_s: float = 2.5):
        await asyncio.sleep(random.uniform(min_s, max_s))

    # ── Session ──────────────────────────────────────────────────────────────────────

    async def authenticate(self) -> bool:
        """
        Multi-strategy authentication:
        1. Try API token (if we have one)
        2. Fall back to browser session validation
        """
        # Strategy 1: API token
        if self.oauth_token:
            try:
                profile = await self._api_get("/me")
                if "id" in profile:
                    return True
            except Exception:
                self.logger.info(
                    f"API token invalid for {self.account_id}, trying browser session"
                )

        # Strategy 2: Validate browser session
        try:
            result = await self._auth_service.validate_session()
            if result.get("valid"):
                return True
        except Exception as e:
            self.logger.error(f"Browser session validation failed: {e}")

        return False

    async def health_check(self) -> dict:
        """
        Enhanced health check that returns profile data when available.
        """
        # Try API first
        if self.oauth_token:
            try:
                profile = await self._api_get("/me")
                return {
                    "valid": True,
                    "platform": "soundcloud",
                    "profile": {
                        "platform_user_id": str(profile.get("id", "")),
                        "username": profile.get("permalink", profile.get("username", "")),
                        "display_name": profile.get("full_name", profile.get("username", "")),
                        "avatar_url": profile.get("avatar_url", ""),
                        "bio": profile.get("description", ""),
                        "follower_count": profile.get("followers_count", 0),
                        "following_count": profile.get("followings_count", 0),
                        "track_count": profile.get("track_count", 0),
                        "likes_count": profile.get("public_favorites_count", 0),
                        "profile_url": profile.get("permalink_url", ""),
                        "is_verified": profile.get("verified", False),
                    },
                }
            except Exception:
                pass

        # Fall back to browser session validation
        try:
            result = await self._auth_service.validate_session()
            return {
                "valid": result.get("valid", False),
                "platform": "soundcloud",
                "profile": result.get("profile"),
                "needs_relogin": result.get("needs_relogin", False),
            }
        except Exception as e:
            return {
                "valid": False,
                "platform": "soundcloud",
                "error": str(e),
                "needs_relogin": True,
            }

    # ── Posting ──────────────────────────────────────────────────────────────────────

    async def create_post(
        self, content: str, media_paths: list = None, metadata: dict = None
    ) -> dict:
        """Post to SoundCloud via browser (no official write API for track descriptions/comments)."""
        raise NotImplementedError("Use upload_audio for SoundCloud track posts.")

    async def upload_audio(
        self, file_path: str, title: str, metadata: dict = None
    ) -> dict:
        """Upload a track via browser automation (Playwright)."""
        meta = metadata or {}
        page = await self._browser_mgr.get_page()
        try:
            await page.goto(
                "https://soundcloud.com/upload", wait_until="networkidle"
            )
            await self._human_delay()

            file_input = page.locator('input[type="file"]')
            await file_input.set_input_files(file_path)
            await self._human_delay(2, 4)

            title_input = page.locator('input[placeholder*="Title"]')
            await title_input.fill(title)
            await self._human_delay()

            if meta.get("genre"):
                genre_input = page.locator('input[placeholder*="Genre"]')
                await genre_input.fill(meta["genre"])
                await self._human_delay()

            if meta.get("description"):
                desc_input = page.locator('textarea[placeholder*="Describe"]')
                await desc_input.fill(meta["description"])
                await self._human_delay()

            save_btn = page.locator('button:has-text("Save")')
            await save_btn.click()
            await page.wait_for_selector(
                ".uploadStatus__status--done", timeout=120_000
            )

            track_url = page.url
            return {
                "platform_post_id": track_url.split("/")[-1],
                "url": track_url,
            }
        finally:
            await self._browser_mgr.release_page(page)

    # ── Engagement ───────────────────────────────────────────────────────────────────

    async def like(self, target_id: str) -> bool:
        """Like a track. target_id = full SoundCloud track URL or numeric ID."""
        try:
            import httpx

            url = f"{SC_API_BASE}/me/likes/tracks/{target_id}"
            headers = {"Authorization": f"OAuth {self.oauth_token}"}
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.put(url, headers=headers)
                return r.status_code in (200, 201)
        except Exception as e:
            self.logger.warning(f"API like failed, trying browser: {e}")
            return await self._browser_like(target_id)

    async def _browser_like(self, track_url: str) -> bool:
        page = await self._browser_mgr.get_page()
        try:
            await page.goto(track_url, wait_until="networkidle")
            await self._human_delay()
            like_btn = page.locator('button.sc-button-like:not(.active)')
            if await like_btn.count() > 0:
                await like_btn.first.click()
                await self._human_delay()
                return True
            return False
        finally:
            await self._browser_mgr.release_page(page)

    async def unlike(self, target_id: str) -> bool:
        import httpx

        url = f"{SC_API_BASE}/me/likes/tracks/{target_id}"
        headers = {"Authorization": f"OAuth {self.oauth_token}"}
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.delete(url, headers=headers)
            return r.status_code in (200, 204)

    async def repost(self, target_id: str) -> bool:
        """Repost a track (API + browser fallback)."""
        try:
            import httpx

            url = f"{SC_API_BASE}/me/track_reposts/{target_id}"
            headers = {"Authorization": f"OAuth {self.oauth_token}"}
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.put(url, headers=headers)
                return r.status_code in (200, 201)
        except Exception as e:
            self.logger.warning(f"API repost failed, trying browser: {e}")
            return await self._browser_repost(target_id)

    async def _browser_repost(self, track_url: str) -> bool:
        page = await self._browser_mgr.get_page()
        try:
            await page.goto(track_url, wait_until="networkidle")
            await self._human_delay()
            more_btn = page.locator("button.sc-button-more")
            await more_btn.first.click()
            await self._human_delay(0.5, 1.2)
            repost_opt = page.locator('button:has-text("Repost")')
            await repost_opt.first.click()
            await self._human_delay()
            return True
        except Exception as e:
            self.logger.error(f"Browser repost failed: {e}")
            return False
        finally:
            await self._browser_mgr.release_page(page)

    async def unrepost(self, target_id: str) -> bool:
        import httpx

        url = f"{SC_API_BASE}/me/track_reposts/{target_id}"
        headers = {"Authorization": f"OAuth {self.oauth_token}"}
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.delete(url, headers=headers)
            return r.status_code in (200, 204)

    async def comment(self, target_id: str, text: str) -> dict:
        """Post a comment on a track."""
        try:
            import httpx

            url = f"{SC_API_BASE}/tracks/{target_id}/comments"
            headers = {
                "Authorization": f"OAuth {self.oauth_token}",
                "Content-Type": "application/json",
            }
            payload = {"comment": {"body": text}}
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.post(url, json=payload, headers=headers)
                r.raise_for_status()
                return {"comment_id": r.json().get("id")}
        except Exception as e:
            self.logger.warning(f"API comment failed, trying browser: {e}")
            return await self._browser_comment(target_id, text)

    async def _browser_comment(self, track_url: str, text: str) -> dict:
        page = await self._browser_mgr.get_page()
        try:
            await page.goto(track_url, wait_until="networkidle")
            await self._human_delay()
            comment_box = page.locator(
                'textarea[placeholder*="Write a comment"]'
            )
            await comment_box.click()
            await self._human_delay(0.3, 0.8)
            await comment_box.fill(text)
            await self._human_delay(0.5, 1.5)
            submit_btn = page.locator("button.commentForm__submit")
            await submit_btn.click()
            await self._human_delay()
            return {"comment_id": None}
        finally:
            await self._browser_mgr.release_page(page)

    async def follow(self, target_user_id: str) -> bool:
        try:
            import httpx

            url = f"{SC_API_BASE}/me/followings/{target_user_id}"
            headers = {"Authorization": f"OAuth {self.oauth_token}"}
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.put(url, headers=headers)
                return r.status_code in (200, 201)
        except Exception as e:
            self.logger.warning(f"API follow failed: {e}")
            return False

    async def unfollow(self, target_user_id: str) -> bool:
        import httpx

        url = f"{SC_API_BASE}/me/followings/{target_user_id}"
        headers = {"Authorization": f"OAuth {self.oauth_token}"}
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.delete(url, headers=headers)
            return r.status_code in (200, 204)

    async def play_track(self, track_id: str) -> bool:
        """Register a play by streaming a chunk via browser."""
        page = await self._browser_mgr.get_page()
        try:
            track_url = (
                track_id
                if track_id.startswith("http")
                else f"https://soundcloud.com/{track_id}"
            )
            await page.goto(track_url, wait_until="networkidle")
            await self._human_delay()
            play_btn = page.locator("button.playButton")
            if await play_btn.count() > 0:
                await play_btn.first.click()
                await asyncio.sleep(random.uniform(5, 15))
                return True
            return False
        finally:
            await self._browser_mgr.release_page(page)

    async def save_track(self, track_id: str) -> bool:
        return await self.like(track_id)

    async def add_to_playlist(self, track_id: str, playlist_id: str) -> bool:
        try:
            import httpx

            url = f"{SC_API_BASE}/playlists/{playlist_id}/tracks"
            headers = {
                "Authorization": f"OAuth {self.oauth_token}",
                "Content-Type": "application/json",
            }
            payload = {"playlist": {"tracks": [{"id": int(track_id)}]}}
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.put(url, json=payload, headers=headers)
                return r.status_code in (200, 201)
        except Exception as e:
            self.logger.error(f"add_to_playlist failed: {e}")
            return False

    # ── Profile / analytics ────────────────────────────────────────────────────────────

    async def get_profile(self) -> dict:
        return await self._api_get("/me")

    async def get_analytics(self, post_id: Optional[str] = None) -> dict:
        if post_id:
            return await self._api_get(f"/tracks/{post_id}")
        profile = await self._api_get("/me")
        return {
            "followers_count": profile.get("followers_count", 0),
            "followings_count": profile.get("followings_count", 0),
            "track_count": profile.get("track_count", 0),
            "public_favorites_count": profile.get("public_favorites_count", 0),
        }

    async def close(self):
        """Clean up browser resources."""
        await self._auth_service.close()
        await self._browser_mgr.close()
