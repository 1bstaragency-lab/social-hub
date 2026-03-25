"""
In-process scheduler using APScheduler.
Replaces Celery Beat + Worker for local dev mode.
Handles: post dispatch, engagement dispatch, analytics, health checks.
"""

import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.core.database import AsyncSessionLocal
from app.models.post import Post, PostStatus
from app.models.social_account import SocialAccount, AccountCredential, AccountStatus
from app.core.security import decrypt_credential
from app.platforms import get_platform_client
from sqlalchemy import select, and_

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler = None


def _run_async(coro):
    """Run async code from a sync APScheduler job."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _dispatch_due_posts():
    """Find and publish all posts with scheduled_at <= now."""
    async def _inner():
        async with AsyncSessionLocal() as db:
            now = datetime.now(timezone.utc)
            q = await db.execute(
                select(Post).where(
                    and_(
                        Post.status == PostStatus.SCHEDULED,
                        Post.scheduled_at <= now,
                    )
                )
            )
            posts = q.scalars().all()
            if not posts:
                return

            logger.info(f"Scheduler: dispatching {len(posts)} due posts")
            for post in posts:
                try:
                    post.status = PostStatus.PUBLISHING
                    await db.commit()

                    account = await db.get(SocialAccount, post.account_id)
                    creds_q = await db.execute(
                        select(AccountCredential).where(
                            AccountCredential.account_id == post.account_id
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

                    media_paths = [m.file_path for m in post.media] if post.media else []

                    if post.post_type.value == "audio":
                        result = await client.upload_audio(
                            file_path=media_paths[0] if media_paths else "",
                            title=post.content_metadata.get("title", "Untitled"),
                            metadata=post.content_metadata,
                        )
                    elif post.post_type.value == "video":
                        result = await client.upload_video(
                            file_path=media_paths[0] if media_paths else "",
                            caption=post.content_text or "",
                            metadata=post.content_metadata,
                        )
                    else:
                        result = await client.create_post(
                            content=post.content_text or "",
                            media_paths=media_paths,
                            metadata=post.content_metadata,
                        )

                    post.status = PostStatus.PUBLISHED
                    post.published_at = datetime.now(timezone.utc)
                    post.platform_post_id = result.get("platform_post_id")
                    post.platform_post_url = result.get("url")
                    logger.info(f"Post {post.id} published.")
                except Exception as e:
                    post.retry_count += 1
                    post.error_message = str(e)
                    post.status = PostStatus.FAILED if post.retry_count >= post.max_retries else PostStatus.SCHEDULED
                    logger.error(f"Post {post.id} failed: {e}")

                await db.commit()

    try:
        _run_async(_inner())
    except Exception as e:
        logger.error(f"Post dispatcher error: {e}")


def _health_check_accounts():
    """Periodic health check on all active accounts."""
    async def _inner():
        async with AsyncSessionLocal() as db:
            q = await db.execute(
                select(SocialAccount).where(
                    SocialAccount.status.in_([AccountStatus.ACTIVE, AccountStatus.NEEDS_REAUTH])
                )
            )
            accounts = q.scalars().all()
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
                        account_id=str(account.id), credentials=creds, proxy=account.proxy_config,
                    )
                    health = await client.health_check()
                    account.last_health_check = datetime.now(timezone.utc)
                    if health.get("valid"):
                        if account.status == AccountStatus.NEEDS_REAUTH:
                            account.status = AccountStatus.ACTIVE
                    else:
                        account.status = AccountStatus.NEEDS_REAUTH
                    db.add(account)
                except Exception as e:
                    logger.error(f"Health check error for {account.id}: {e}")
            await db.commit()

    try:
        _run_async(_inner())
    except Exception as e:
        logger.error(f"Health check error: {e}")


def start_scheduler():
    global _scheduler
    _scheduler = BackgroundScheduler()

    # Dispatch due posts every 30 seconds
    _scheduler.add_job(
        _dispatch_due_posts,
        IntervalTrigger(seconds=30),
        id="dispatch_posts",
        replace_existing=True,
    )

    # Health checks every 30 minutes
    _scheduler.add_job(
        _health_check_accounts,
        IntervalTrigger(minutes=30),
        id="health_checks",
        replace_existing=True,
    )

    _scheduler.start()
    logger.info("APScheduler started with 2 jobs.")


def stop_scheduler():
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("APScheduler stopped.")
