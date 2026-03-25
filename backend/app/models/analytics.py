"""
Analytics models — snapshots and events per account/post.
Snapshots capture a point-in-time state (followers, reach, etc.)
Events track individual engagement actions (like, comment, share, play).
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Enum as SQLEnum, Integer, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.core.database import Base
from app.core.compat import GUID, JSONType


class SnapshotInterval(str, enum.Enum):
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"


class AnalyticsSnapshot(Base):
    """
    Periodic snapshot of an account's key metrics.
    Used to track growth over time and power the dashboard charts.
    """
    __tablename__ = "analytics_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("social_accounts.id", ondelete="CASCADE"), index=True
    )
    interval: Mapped[SnapshotInterval] = mapped_column(
        SQLEnum(SnapshotInterval), default=SnapshotInterval.DAILY, index=True
    )
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )

    # Growth metrics
    followers_count: Mapped[int] = mapped_column(Integer, default=0)
    following_count: Mapped[int] = mapped_column(Integer, default=0)
    followers_gained: Mapped[int] = mapped_column(Integer, default=0)
    followers_lost: Mapped[int] = mapped_column(Integer, default=0)

    # Content metrics
    posts_count: Mapped[int] = mapped_column(Integer, default=0)
    total_likes: Mapped[int] = mapped_column(Integer, default=0)
    total_comments: Mapped[int] = mapped_column(Integer, default=0)
    total_shares: Mapped[int] = mapped_column(Integer, default=0)
    total_views: Mapped[int] = mapped_column(Integer, default=0)
    total_plays: Mapped[int] = mapped_column(Integer, default=0)

    # Engagement rate (likes+comments+shares / followers * 100)
    engagement_rate: Mapped[float] = mapped_column(Float, default=0.0)

    # Platform-specific extras stored as JSONB
    platform_data: Mapped[dict] = mapped_column(JSONType, default=dict)

    # Relationships
    account = relationship("SocialAccount", back_populates="analytics_snapshots")


class AnalyticsEvent(Base):
    """
    Individual post-level engagement events, synced from platforms.
    """
    __tablename__ = "analytics_events"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    post_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("posts.id", ondelete="CASCADE"), index=True
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("social_accounts.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # like, comment, share, play, view, follow, unfollow, click, save
    event_count: Mapped[int] = mapped_column(Integer, default=1)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
    extra: Mapped[dict] = mapped_column(JSONType, default=dict)
