from pydantic import BaseModel
from typing import Optional, List
from uuid import UUID
from datetime import datetime
from app.models.post import PostStatus, PostType


class PostMediaIn(BaseModel):
    media_type: str
    file_path: str
    mime_type: Optional[str] = None


class PostCreate(BaseModel):
    account_id: UUID
    campaign_id: Optional[UUID] = None
    post_type: PostType
    content_text: Optional[str] = None
    content_metadata: Optional[dict] = {}
    scheduled_at: Optional[datetime] = None
    media: Optional[List[PostMediaIn]] = []
    cross_post_group_id: Optional[UUID] = None  # Link posts across platforms


class PostUpdate(BaseModel):
    content_text: Optional[str] = None
    content_metadata: Optional[dict] = None
    scheduled_at: Optional[datetime] = None
    status: Optional[PostStatus] = None


class PostOut(BaseModel):
    id: UUID
    account_id: UUID
    campaign_id: Optional[UUID]
    post_type: PostType
    status: PostStatus
    content_text: Optional[str]
    platform_post_id: Optional[str]
    platform_post_url: Optional[str]
    scheduled_at: Optional[datetime]
    published_at: Optional[datetime]
    likes_count: int
    comments_count: int
    shares_count: int
    views_count: int
    plays_count: int
    error_message: Optional[str]
    retry_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Engagement actions ──────────────────────────────────────────────────────

class EngagementActionType(str):
    LIKE       = "like"
    UNLIKE     = "unlike"
    REPOST     = "repost"
    UNREPOST   = "unrepost"
    COMMENT    = "comment"
    FOLLOW     = "follow"
    UNFOLLOW   = "unfollow"
    PLAY       = "play"          # SoundCloud / Spotify
    SAVE       = "save"          # Save/bookmark track
    ADD_TO_PLAYLIST = "add_to_playlist"


class EngagementActionCreate(BaseModel):
    account_id: UUID
    action_type: str               # one of EngagementActionType values
    target_url: Optional[str] = None   # URL of the target post/track/profile
    target_platform_id: Optional[str] = None  # Platform-specific ID
    comment_text: Optional[str] = None        # Required if action_type == "comment"
    playlist_id: Optional[str] = None         # Required if action_type == "add_to_playlist"
    scheduled_at: Optional[datetime] = None   # None = execute immediately


class EngagementActionOut(BaseModel):
    id: UUID
    account_id: UUID
    action_type: str
    target_url: Optional[str]
    status: str
    scheduled_at: Optional[datetime]
    executed_at: Optional[datetime]
    error_message: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Bulk engagement ─────────────────────────────────────────────────────────

class BulkEngagementCreate(BaseModel):
    """
    Fire the same engagement action across multiple accounts at once,
    with optional random delay between each to mimic organic behaviour.
    """
    account_ids: List[UUID]
    action_type: str
    target_url: Optional[str] = None
    target_platform_id: Optional[str] = None
    comment_text: Optional[str] = None
    delay_min_seconds: int = 5
    delay_max_seconds: int = 30
    scheduled_at: Optional[datetime] = None
