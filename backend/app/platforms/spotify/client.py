"""
Spotify client — uses the official Spotipy library (OAuth2).
Supports: follow artist, save track, add to playlist, play (via playback API).
"""

import logging
from typing import Optional

from app.platforms.base import BasePlatformClient

logger = logging.getLogger(__name__)


class SpotifyClient(BasePlatformClient):

    def __init__(self, account_id: str, credentials: dict, proxy: Optional[dict] = None):
        super().__init__(account_id, credentials, proxy)
        self.access_token = credentials.get("access_token")
        self.refresh_token = credentials.get("refresh_token")
        self.client_id = credentials.get("client_id")
        self.client_secret = credentials.get("client_secret")
        self._sp = None

    def _get_sp(self):
        if not self._sp:
            import spotipy
            from spotipy.oauth2 import SpotifyOAuth
            self._sp = spotipy.Spotify(auth=self.access_token)
        return self._sp

    async def _async(self, fn, *args, **kwargs):
        import asyncio
        return await asyncio.get_event_loop().run_in_executor(None, lambda: fn(*args, **kwargs))

    # ── Session ──────────────────────────────────────────────────────────────

    async def authenticate(self) -> bool:
        try:
            sp = self._get_sp()
            me = await self._async(sp.me)
            return me is not None
        except Exception as e:
            self.logger.error(f"Spotify auth failed: {e}")
            return False

    async def health_check(self) -> dict:
        valid = await self.authenticate()
        return {"valid": valid, "platform": "spotify"}

    # ── Posting (Spotify doesn't support content posts) ──────────────────────

    async def create_post(self, content: str, media_paths: list = None, metadata: dict = None) -> dict:
        raise NotImplementedError("Spotify does not support creating posts.")

    # ── Engagement ───────────────────────────────────────────────────────────

    async def like(self, target_id: str) -> bool:
        """Save a track to user's library (Spotify's equivalent of 'like')."""
        return await self.save_track(target_id)

    async def unlike(self, target_id: str) -> bool:
        sp = self._get_sp()
        await self._async(sp.current_user_saved_tracks_delete, [target_id])
        return True

    async def repost(self, target_id: str) -> bool:
        raise NotImplementedError("Spotify does not support reposts.")

    async def unrepost(self, target_id: str) -> bool:
        raise NotImplementedError("Spotify does not support reposts.")

    async def comment(self, target_id: str, text: str) -> dict:
        raise NotImplementedError("Spotify does not support comments.")

    async def follow(self, target_user_id: str) -> bool:
        """Follow an artist or user."""
        try:
            sp = self._get_sp()
            # Try as artist first, fall back to user
            try:
                await self._async(sp.user_follow_artists, [target_user_id])
            except Exception:
                await self._async(sp.user_follow_users, [target_user_id])
            return True
        except Exception as e:
            self.logger.error(f"Spotify follow failed: {e}")
            return False

    async def unfollow(self, target_user_id: str) -> bool:
        try:
            sp = self._get_sp()
            try:
                await self._async(sp.user_unfollow_artists, [target_user_id])
            except Exception:
                await self._async(sp.user_unfollow_users, [target_user_id])
            return True
        except Exception as e:
            self.logger.error(f"Spotify unfollow failed: {e}")
            return False

    async def save_track(self, track_id: str) -> bool:
        try:
            sp = self._get_sp()
            await self._async(sp.current_user_saved_tracks_add, [track_id])
            return True
        except Exception as e:
            self.logger.error(f"Spotify save_track failed: {e}")
            return False

    async def play_track(self, track_id: str) -> bool:
        """Start playback (requires Spotify Premium + active device)."""
        try:
            sp = self._get_sp()
            await self._async(sp.start_playback, uris=[f"spotify:track:{track_id}"])
            return True
        except Exception as e:
            self.logger.warning(f"Spotify play_track failed (may need Premium): {e}")
            return False

    async def add_to_playlist(self, track_id: str, playlist_id: str) -> bool:
        try:
            sp = self._get_sp()
            await self._async(
                sp.playlist_add_items,
                playlist_id,
                [f"spotify:track:{track_id}"],
            )
            return True
        except Exception as e:
            self.logger.error(f"Spotify add_to_playlist failed: {e}")
            return False

    # ── Profile / analytics ──────────────────────────────────────────────────

    async def get_profile(self) -> dict:
        sp = self._get_sp()
        return await self._async(sp.me)

    async def get_analytics(self, post_id: Optional[str] = None) -> dict:
        """Spotify doesn't expose analytics via public API."""
        if post_id:
            sp = self._get_sp()
            return await self._async(sp.track, post_id)
        return {}
