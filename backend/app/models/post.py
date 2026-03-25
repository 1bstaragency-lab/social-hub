"""
Post model — content that gets published to social platforms.
Supports scheduling, multi-platform cross-posting, and media attachments.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Enum as SQLEnum, Text, Integer, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.core.database import Base
from app.core.compat import GUID, JSONType


class PostStatus(str, enum.Enum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    QUEUED = "queued"        # Picked up by scheduler, waiting to execute
    PUBLISHING = "publishing"  # Currently being posted
    PUBLISHED = "published"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PostType(str, enum.Enum):
    TEXT = "text"            # Twitter text post
    IMAGE = "image"          # Image post
    VIDEO = "video"          # Video post (TikTok, Twitter)
    AUDIO = "audio"          # Audio upload (SoundCloud)
    REPOST = "repost"        # Repost/retweet
    STORY = "story"          # Stories (where supported)
    PLAYLIST_ADD = "playlist_add"  # Add track to playlist (Spotify, SoundCloud)


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(), primary_key=True, default=uuid.uuid4
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("social_accounts.id", ondelete="CASCADE"), index=True
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("campaigns.id", ondelete="SET NULL"),
        nullable=True, index=True
    )
    # Cross-post grouping: posts with the same group_id are part of the same cross-post
    cross_post_group_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), nullable=True, index=True
    )
    post_type: Mapped[PostType] = mapped_column(SQLEnum(PostType), nullable=False)
    status: Mapped[PostStatus] = mapped_column(
        SQLEnum(PostStatus), default=PostStatus.DRAFT, index=True
    )
    content_text: Mapped[str] = mapped_column(Text, nullable=True)
    content_metadata: Mapped[dict] = mapped_column(JSONType, default=dict)
    # Platform-specific post ID after publishing
    platform_post_id: Mapped[str] = mapped_column(String(255), nullable=True)
    platform_post_url: Mapped[str] = mapped_column(String(500), nullable=True)
    # Scheduling
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    # Error tracking
    error_message: Mapped[str] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    # Engagement metrics (cached from analytics)
    likes_count: Mapped[int] = mapped_column(Integer, default=0)
    comments_count: Mapped[int] = mapped_column(Integer, default=0)
    shares_count: Mapped[int] = mapped_column(Integer, default=0)
    views_count: Mapped[int] = mapped_column(Integer, default=0)
    plays_count: Mapped[int] = mapped_column(Integer, default=0)  # Audio/video plays
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    account = relationship("SocialAccount", back_populates="posts")
    campaign = relationship("Campaign", back_populates="posts")
    media = relationship("PostMedia", back_populates="post", cascade="all, delete-orphan")
    schedule = relationship("PostSchedule", back_populates="post", uselist=False)


class PostMedia(Base):
    __tablename__ = "post_media"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(), primary_key=True, default=uuid.uuid4
    )
    post_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("posts.id", ondelete="CASCADE"), index=True
    )
    media_type: Mapped[str] = mapped_column(String(50), nullable=False)  # image, video, audio
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_url: Mapped[str] = mapped_column(String(500), nullable=True)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=True)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=True)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=True)  # For audio/video
    thumbnail_path: Mapped[str] = mapped_column(String(500), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONType, default=dict)

    # Relationships
    post = relationship("Post", back_populates="media")


class PostSchedule(Base):
    """Advanced scheduling options beyond simple scheduled_at."""
    __tablename__ = "post_schedules"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(), primary_key=True, default=uuid.uuid4
    )
    post_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("posts.id", ondelete="CASCADE"), unique=True
    )
    timezone: Mapped[str] = mapped_column(String(50), default="UTC")
    # Recurring post support
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False)
    cron_expression: Mapped[str] = mapped_column(String(100), nullable=True)
    recurrence_end_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    # Optimal time posting
    use_optimal_time: Mapped[bool] = mapped_column(Boolean, default=False)
    optimal_time_window_hours: Mapped[int] = mapped_column(Integer, default=4)

    # Relationships
    post = relationship("Post", back_populates="schedule")
