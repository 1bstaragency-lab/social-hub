"""
Celery tasks for collecting analytics snapshots from all active accounts.
"""

import asyncio
import logging
from datetime import datetime, timezone

from app.workers.celery_app import celery_app
from app.core.database import AsyncSessionLocal
from app.models.social_account import SocialAccount, AccountCredential, AccountStatus
from app.models.analytics import AnalyticsSnapshot, SnapshotInterval
from app.core.security import decrypt_credential
from app.platforms import get_platform_client
from sqlalchemy import select

logger = logging.getLogger(__name__)


def run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(name="app.workers.tasks.analytics.collect_snapshots", bind=True)
def collect_snapshots(self, interval: str = "daily"):
    """Collect analytics snapshots for all active accounts."""
    async def _collect():
        async with AsyncSessionLocal() as db:
            q = await db.execute(
                select(SocialAccount).where(SocialAccount.status == AccountStatus.ACTIVE)
            )
            accounts = q.scalars().all()
            logger.info(f"Collecting {interval} analytics for {len(accounts)} accounts")

            for account in accounts:
                try:
                    creds_q = await db.execute(
                        select(AccountCredential).where(
                            AccountCredential.account_id == account.id
                        )
                    )
                    creds = {c.credential_type: decrypt_credential(c.encrypted_value)
                             for c in creds_q.scalars().all()}

                    client_class = get_platform_client(account.platform)
                    client = client_class(
                        account_id=str(account.id),
                        credentials=creds,
                        proxy=account.proxy_config,
                    )

                    data = await client.get_analytics()

                    snapshot = AnalyticsSnapshot(
                        account_id=account.id,
                        interval=SnapshotInterval(interval),
                        captured_at=datetime.now(timezone.utc),
                        followers_count=data.get("followers_count", 0),
                        following_count=data.get("followings_count", 0),
                        total_plays=data.get("playback_count", 0),
                        total_likes=data.get("likes_count", 0),
                        total_views=data.get("reposts_count", 0),
                        platform_data=data,
                    )
                    db.add(snapshot)

                    # Update account follower count
                    if data.get("followers_count"):
                        account.follower_count = data["followers_count"]
                        db.add(account)

                except Exception as e:
                    logger.error(f"Analytics collection failed for {account.id}: {e}")

            await db.commit()
            logger.info(f"Analytics snapshots collected for {len(accounts)} accounts.")

    run_async(_collect())
