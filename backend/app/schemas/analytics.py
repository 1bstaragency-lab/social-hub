from pydantic import BaseModel
from typing import Optional, List
from uuid import UUID
from datetime import datetime


class AnalyticsSnapshotOut(BaseModel):
    id: UUID
    account_id: UUID
    interval: str
    captured_at: datetime
    followers_count: int
    followers_gained: int
    followers_lost: int
    total_likes: int
    total_comments: int
    total_shares: int
    total_views: int
    total_plays: int
    engagement_rate: float
    platform_data: dict

    model_config = {"from_attributes": True}


class GrowthChartPoint(BaseModel):
    date: datetime
    followers: int
    engagement_rate: float
    posts: int
    plays: int


class AccountSummary(BaseModel):
    account_id: UUID
    platform: str
    username: str
    followers: int
    engagement_rate: float
    posts_last_7d: int
    plays_last_7d: int
    top_post_url: Optional[str] = None


class DashboardOverview(BaseModel):
    total_accounts: int
    active_accounts: int
    total_posts_scheduled: int
    total_posts_published_today: int
    total_followers: int
    avg_engagement_rate: float
    pending_actions: int
    accounts_needing_reauth: int
    account_summaries: List[AccountSummary]
