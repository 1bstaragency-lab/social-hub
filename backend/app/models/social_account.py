"""
Social account model — individual platform accounts with encrypted credentials.
Each account maintains isolated session state for browser automation.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Enum as SQLEnum, Text, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.core.database import Base
from app.core.compat import GUID, JSONType


class Platform(str, enum.Enum):
    SOUNDCLOUD = "soundcloud"
    TIKTOK = "tiktok"
    TWITTER = "twitter"
    SPOTIFY = "spotify"


class AccountStatus(str, enum.Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    SUSPENDED = "suspended"
    NEEDS_REAUTH = "needs_reauth"
    DISABLED = "disabled"


class AuthMethod(str, enum.Enum):
    API_TOKEN = "api_token"           # Official API (Twitter, Spotify)
    OAUTH2 = "oauth2"                 # OAuth flow
    BROWSER_SESSION = "browser_session"  # Playwright session (SoundCloud, TikTok)
    COOKIE_BASED = "cookie_based"     # Stored cookies


class SocialAccount(Base):
    __tablename__ = "social_accounts"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    platform: Mapped[Platform] = mapped_column(SQLEnum(Platform), nullable=False, index=True)
    platform_user_id: Mapped[str] = mapped_column(String(255), nullable=True)
    username: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[str] = mapped_column(String(500), nullable=True)
    bio: Mapped[str] = mapped_column(Text, nullable=True)
    status: Mapped[AccountStatus] = mapped_column(
        SQLEnum(AccountStatus), default=AccountStatus.ACTIVE
    )
    auth_method: Mapped[AuthMethod] = mapped_column(SQLEnum(AuthMethod), nullable=False)
    proxy_config: Mapped[dict] = mapped_column(JSONType, nullable=True)  # Per-account proxy
    rate_limit_config: Mapped[dict] = mapped_column(
        JSONType, default=lambda: {"posts_per_day": 10, "actions_per_hour": 30}
    )
    metadata_: Mapped[dict] = mapped_column("metadata", JSONType, default=dict)
    follower_count: Mapped[int] = mapped_column(Integer, default=0)
    following_count: Mapped[int] = mapped_column(Integer, default=0)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    last_active_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    last_health_check: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    organization = relationship("Organization", back_populates="social_accounts")
    credentials = relationship(
        "AccountCredential", back_populates="account", cascade="all, delete-orphan"
    )
    posts = relationship("Post", back_populates="account")
    analytics_snapshots = relationship("AnalyticsSnapshot", back_populates="account")


class AccountCredential(Base):
    """
    Encrypted credential storage. Supports multiple credential types per account.
    All sensitive values are encrypted at rest using Fernet symmetric encryption.
    """
    __tablename__ = "account_credentials"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(), primary_key=True, default=uuid.uuid4
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("social_accounts.id", ondelete="CASCADE"), index=True
    )
    credential_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # "api_key", "access_token", "refresh_token", "session_cookies", "password"
    encrypted_value: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    account = relationship("SocialAccount", back_populates="credentials")
