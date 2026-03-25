"""
TikTok client — browser automation (Playwright) as primary method.
TikTok's official API is extremely limited for posting/engagement,
so all actions go through a real browser session.
"""

import asyncio
import random
import logging
from typing import Optional

from app.platforms.base import BasePlatformClient
from app.services.browser_session import BrowserSessionManager

logger = logging.getLogger(__name__)


class TikTokClient(BasePlatformClient):

    def __init__(self, account_id: str, credentials: dict, proxy: Optional[dict] = None):
        super().__init__(account_id, credentials, proxy)
        self._browser_mgr = BrowserSessionManager(account_id, proxy=proxy)

    async def _human_delay(self, min_s=1.0, max_s=3.5):
        await asyncio.sleep(random.uniform(min_s, max_s))

    # ── Session ──────────────────────────────────────────────────────────────

    async def authenticate(self) -> bool:
        """Check that the stored session cookie is still valid."""
        page = await self._browser_mgr.get_page()
        try:
            await page.goto("https://www.tiktok.com/foryou", wait_until="networkidle")
            await self._human_delay()
            # If logged in, there's no login button
            login_btn = page.locator('a[href="/login"]')
            logged_in = await login_btn.count() == 0
            return logged_in
        except Exception as e:
            self.logger.error(f"TikTok auth check failed: {e}")
            return False
        finally:
            await self._browser_mgr.release_page(page)

    async def health_check(self) -> dict:
        valid = await self.authenticate()
        return {"valid": valid, "platform": "tiktok"}

    # ── Posting ──────────────────────────────────────────────────────────────

    async def create_post(self, content: str, media_paths: list = None, metadata: dict = None) -> dict:
        return await self.upload_video(
            file_path=media_paths[0] if media_paths else "",
            caption=content,
            metadata=metadata or {},
        )

    async def upload_video(self, file_path: str, caption: str, metadata: dict = None) -> dict:
        meta = metadata or {}
        page = await self._browser_mgr.get_page()
        try:
            await page.goto("https://www.tiktok.com/upload", wait_until="networkidle")
            await self._human_delay(2, 4)

            # Upload file
            file_input = page.locator('input[type="file"]')
            await file_input.set_input_files(file_path)
            await self._human_delay(3, 6)

            # Caption
            caption_box = page.locator('div[contenteditable="true"]').first
            await caption_box.click()
            await caption_box.fill(caption)
            await self._human_delay()

            # Hashtags
            if meta.get("hashtags"):
                for tag in meta["hashtags"][:5]:
                    await caption_box.type(f" #{tag}")
                    await self._human_delay(0.3, 0.7)

            # Post
            post_btn = page.locator('button:has-text("Post")')
            await post_btn.click()
            await page.wait_for_url("**/upload**success**", timeout=60_000)
            return {"platform_post_id": None, "url": "https://www.tiktok.com/upload"}
        finally:
            await self._browser_mgr.release_page(page)

    # ── Engagement ───────────────────────────────────────────────────────────

    async def like(self, target_id: str) -> bool:
        """Like a TikTok video by its URL."""
        page = await self._browser_mgr.get_page()
        try:
            url = target_id if target_id.startswith("http") else f"https://www.tiktok.com/@_/video/{target_id}"
            await page.goto(url, wait_until="networkidle")
            await self._human_delay(1.5, 3.0)
            like_btn = page.locator('[data-e2e="like-icon"]').first
            await like_btn.click()
            await self._human_delay()
            return True
        except Exception as e:
            self.logger.error(f"TikTok like failed: {e}")
            return False
        finally:
            await self._browser_mgr.release_page(page)

    async def unlike(self, target_id: str) -> bool:
        # Same as like (toggle)
        return await self.like(target_id)

    async def repost(self, target_id: str) -> bool:
        """Use TikTok's native repost button."""
        page = await self._browser_mgr.get_page()
        try:
            url = target_id if target_id.startswith("http") else f"https://www.tiktok.com/@_/video/{target_id}"
            await page.goto(url, wait_until="networkidle")
            await self._human_delay(1.5, 3.0)
            share_btn = page.locator('[data-e2e="share-icon"]').first
            await share_btn.click()
            await self._human_delay(0.5, 1.5)
            repost_btn = page.locator('p:has-text("Repost")').first
            await repost_btn.click()
            await self._human_delay()
            return True
        except Exception as e:
            self.logger.error(f"TikTok repost failed: {e}")
            return False
        finally:
            await self._browser_mgr.release_page(page)

    async def unrepost(self, target_id: str) -> bool:
        return await self.repost(target_id)  # Toggle

    async def comment(self, target_id: str, text: str) -> dict:
        page = await self._browser_mgr.get_page()
        try:
            url = target_id if target_id.startswith("http") else f"https://www.tiktok.com/@_/video/{target_id}"
            await page.goto(url, wait_until="networkidle")
            await self._human_delay(1.5, 3.0)
            comment_input = page.locator('[data-e2e="comment-input"]').first
            await comment_input.click()
            await self._human_delay(0.5, 1.0)
            await comment_input.fill(text)
            await self._human_delay(0.5, 1.5)
            await page.keyboard.press("Enter")
            await self._human_delay()
            return {"comment_id": None}
        finally:
            await self._browser_mgr.release_page(page)

    async def follow(self, target_user_id: str) -> bool:
        """target_user_id can be a username or profile URL."""
        page = await self._browser_mgr.get_page()
        try:
            url = target_user_id if target_user_id.startswith("http") else f"https://www.tiktok.com/@{target_user_id}"
            await page.goto(url, wait_until="networkidle")
            await self._human_delay(1.5, 3.0)
            follow_btn = page.locator('[data-e2e="follow-button"]:has-text("Follow")').first
            await follow_btn.click()
            await self._human_delay()
            return True
        except Exception as e:
            self.logger.error(f"TikTok follow failed: {e}")
            return False
        finally:
            await self._browser_mgr.release_page(page)

    async def unfollow(self, target_user_id: str) -> bool:
        page = await self._browser_mgr.get_page()
        try:
            url = target_user_id if target_user_id.startswith("http") else f"https://www.tiktok.com/@{target_user_id}"
            await page.goto(url, wait_until="networkidle")
            await self._human_delay()
            unfollow_btn = page.locator('[data-e2e="follow-button"]:has-text("Following")').first
            await unfollow_btn.click()
            await self._human_delay(0.3, 0.8)
            confirm_btn = page.locator('button:has-text("Unfollow")').first
            if await confirm_btn.count() > 0:
                await confirm_btn.click()
            await self._human_delay()
            return True
        except Exception as e:
            self.logger.error(f"TikTok unfollow failed: {e}")
            return False
        finally:
            await self._browser_mgr.release_page(page)

    # ── Profile / analytics ──────────────────────────────────────────────────

    async def get_profile(self) -> dict:
        page = await self._browser_mgr.get_page()
        try:
            await page.goto("https://www.tiktok.com/profile", wait_until="networkidle")
            await self._human_delay()
            followers = await page.locator('[data-e2e="followers-count"]').first.inner_text()
            following = await page.locator('[data-e2e="following-count"]').first.inner_text()
            likes = await page.locator('[data-e2e="likes-count"]').first.inner_text()
            return {"followers": followers, "following": following, "likes": likes}
        finally:
            await self._browser_mgr.release_page(page)

    async def get_analytics(self, post_id: Optional[str] = None) -> dict:
        return await self.get_profile()
