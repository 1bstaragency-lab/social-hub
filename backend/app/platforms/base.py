"""
Abstract base class for all platform clients.
Every platform must implement these engagement and posting methods.
"""

from abc import ABC, abstractmethod
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class BasePlatformClient(ABC):
    """
    All platform clients inherit from this. Each method raises NotImplementedError
    if the platform doesn't support that action, allowing callers to handle gracefully.
    """

    def __init__(self, account_id: str, credentials: dict, proxy: Optional[dict] = None):
        self.account_id = account_id
        self.credentials = credentials
        self.proxy = proxy
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    # ── Session management ───────────────────────────────────────────────────

    @abstractmethod
    async def authenticate(self) -> bool:
        """Verify credentials / refresh token / restore session."""
        ...

    @abstractmethod
    async def health_check(self) -> dict:
        """Return dict with 'valid': bool and optional 'error': str."""
        ...

    # ── Content posting ──────────────────────────────────────────────────────

    @abstractmethod
    async def create_post(self, content: str, media_paths: list = None, metadata: dict = None) -> dict:
        """Publish a post. Returns {'platform_post_id': ..., 'url': ...}."""
        ...

    async def upload_audio(self, file_path: str, title: str, metadata: dict = None) -> dict:
        raise NotImplementedError(f"{self.__class__.__name__} does not support audio uploads.")

    async def upload_video(self, file_path: str, caption: str, metadata: dict = None) -> dict:
        raise NotImplementedError(f"{self.__class__.__name__} does not support video uploads.")

    # ── Engagement actions ───────────────────────────────────────────────────

    @abstractmethod
    async def like(self, target_id: str) -> bool:
        """Like a post/track by its platform ID."""
        ...

    @abstractmethod
    async def unlike(self, target_id: str) -> bool:
        ...

    @abstractmethod
    async def repost(self, target_id: str) -> bool:
        """Repost / retweet / reblog a post."""
        ...

    @abstractmethod
    async def unrepost(self, target_id: str) -> bool:
        ...

    @abstractmethod
    async def comment(self, target_id: str, text: str) -> dict:
        """Post a comment. Returns {'comment_id': ...}."""
        ...

    @abstractmethod
    async def follow(self, target_user_id: str) -> bool:
        """Follow a user/artist."""
        ...

    @abstractmethod
    async def unfollow(self, target_user_id: str) -> bool:
        ...

    async def play_track(self, track_id: str) -> bool:
        """Register a play on a track (SoundCloud/Spotify)."""
        raise NotImplementedError(f"{self.__class__.__name__} does not support play_track.")

    async def save_track(self, track_id: str) -> bool:
        """Save/bookmark a track."""
        raise NotImplementedError(f"{self.__class__.__name__} does not support save_track.")

    async def add_to_playlist(self, track_id: str, playlist_id: str) -> bool:
        """Add a track to a playlist."""
        raise NotImplementedError(f"{self.__class__.__name__} does not support add_to_playlist.")

    # ── Profile / analytics ─────────────────────────────────────────────────

    @abstractmethod
    async def get_profile(self) -> dict:
        """Fetch current account profile data."""
        ...

    @abstractmethod
    async def get_analytics(self, post_id: Optional[str] = None) -> dict:
        """Fetch engagement metrics for account or a specific post."""
        ...
