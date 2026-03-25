from pydantic import BaseModel, HttpUrl
from typing import Optional
from uuid import UUID
from datetime import datetime
from app.models.social_account import Platform, AccountStatus, AuthMethod


class SocialAccountBase(BaseModel):
    platform: Platform
    username: str
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    auth_method: AuthMethod
    proxy_config: Optional[dict] = None
    rate_limit_config: Optional[dict] = None


class SocialAccountCreate(SocialAccountBase):
    organization_id: UUID
    credentials: dict  # {"api_key": "...", "access_token": "...", etc.}


class SocialAccountUpdate(BaseModel):
    display_name: Optional[str] = None
    status: Optional[AccountStatus] = None
    proxy_config: Optional[dict] = None
    rate_limit_config: Optional[dict] = None


class SocialAccountOut(SocialAccountBase):
    id: UUID
    organization_id: UUID
    platform_user_id: Optional[str]
    status: AccountStatus
    follower_count: int
    following_count: int
    is_verified: bool
    last_active_at: Optional[datetime]
    last_health_check: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


class AccountHealthStatus(BaseModel):
    account_id: UUID
    platform: Platform
    username: str
    status: AccountStatus
    session_valid: bool
    last_checked: datetime
    error: Optional[str] = None
