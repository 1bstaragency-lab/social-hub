from uuid import UUID
from typing import List, Optional
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.models.analytics import AnalyticsSnapshot
from app.models.post import Post, PostStatus
from app.models.social_account import SocialAccount, AccountStatus
from app.schemas.analytics import (
    AnalyticsSnapshotOut, GrowthChartPoint, DashboardOverview, AccountSummary
)

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/dashboard", response_model=DashboardOverview)
async def dashboard_overview(
    organization_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Top-level dashboard numbers."""
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = now - timedelta(days=7)

    # Account counts
    acct_q = select(SocialAccount)
    if organization_id:
        acct_q = acct_q.where(SocialAccount.organization_id == organization_id)
    all_accounts = (await db.execute(acct_q)).scalars().all()

    total_accounts = len(all_accounts)
    active_accounts = sum(1 for a in all_accounts if a.status == AccountStatus.ACTIVE)
    needs_reauth = sum(1 for a in all_accounts if a.status == AccountStatus.NEEDS_REAUTH)
    total_followers = sum(a.follower_count for a in all_accounts)

    # Post counts
    scheduled_count = (await db.execute(
        select(func.count(Post.id)).where(Post.status == PostStatus.SCHEDULED)
    )).scalar_one()

    published_today = (await db.execute(
        select(func.count(Post.id)).where(
            Post.status == PostStatus.PUBLISHED,
            Post.published_at >= today_start,
        )
    )).scalar_one()

    # Avg engagement rate from latest snapshots
    latest_snapshots = []
    for acct in all_accounts:
        snap = (await db.execute(
            select(AnalyticsSnapshot)
            .where(AnalyticsSnapshot.account_id == acct.id)
            .order_by(AnalyticsSnapshot.captured_at.desc())
            .limit(1)
        )).scalar_one_or_none()
        if snap:
            latest_snapshots.append(snap)

    avg_engagement = (
        sum(s.engagement_rate for s in latest_snapshots) / len(latest_snapshots)
        if latest_snapshots else 0.0
    )

    # Per-account summaries
    summaries = []
    for acct in all_accounts[:20]:  # Cap at 20 for performance
        posts_7d = (await db.execute(
            select(func.count(Post.id)).where(
                Post.account_id == acct.id,
                Post.published_at >= week_ago,
                Post.status == PostStatus.PUBLISHED,
            )
        )).scalar_one()

        snap = next((s for s in latest_snapshots if s.account_id == acct.id), None)
        summaries.append(AccountSummary(
            account_id=acct.id,
            platform=acct.platform.value,
            username=acct.username,
            followers=acct.follower_count,
            engagement_rate=snap.engagement_rate if snap else 0.0,
            posts_last_7d=posts_7d,
            plays_last_7d=snap.total_plays if snap else 0,
        ))

    return DashboardOverview(
        total_accounts=total_accounts,
        active_accounts=active_accounts,
        total_posts_scheduled=scheduled_count,
        total_posts_published_today=published_today,
        total_followers=total_followers,
        avg_engagement_rate=round(avg_engagement, 2),
        pending_actions=0,
        accounts_needing_reauth=needs_reauth,
        account_summaries=summaries,
    )


@router.get("/accounts/{account_id}/growth", response_model=List[GrowthChartPoint])
async def account_growth(
    account_id: UUID,
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Return daily follower + engagement data for chart rendering."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    q = await db.execute(
        select(AnalyticsSnapshot)
        .where(
            AnalyticsSnapshot.account_id == account_id,
            AnalyticsSnapshot.captured_at >= since,
            AnalyticsSnapshot.interval == "daily",
        )
        .order_by(AnalyticsSnapshot.captured_at.asc())
    )
    snaps = q.scalars().all()
    return [
        GrowthChartPoint(
            date=s.captured_at,
            followers=s.followers_count,
            engagement_rate=s.engagement_rate,
            posts=s.posts_count,
            plays=s.total_plays,
        )
        for s in snaps
    ]


@router.get("/accounts/{account_id}/snapshots", response_model=List[AnalyticsSnapshotOut])
async def account_snapshots(
    account_id: UUID,
    interval: Optional[str] = Query("daily"),
    limit: int = Query(30),
    db: AsyncSession = Depends(get_db),
):
    q = await db.execute(
        select(AnalyticsSnapshot)
        .where(
            AnalyticsSnapshot.account_id == account_id,
            AnalyticsSnapshot.interval == interval,
        )
        .order_by(AnalyticsSnapshot.captured_at.desc())
        .limit(limit)
    )
    return q.scalars().all()
