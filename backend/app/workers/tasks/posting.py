"""
Celery tasks for post publishing and scheduling.
"""

import asyncio
import logging
from uuid import UUID
from datetime import datetime, timezone

from celery import shared_task
from sqlalchemy import select, and_

from app.workers.celery_app import celery_app
from app.core.database import AsyncSessionLocal
from app.models.post import Post, PostStatus
from app.models.social_account import SocialAccount, AccountCredential
from app.core.security import decrypt_credential
from app.platforms import get_platform_client

logger = logging.getLogger(__name__)


def run_async(coro):
    """Run an async coroutine in a Celery (sync) task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(name="app.workers.tasks.posting.dispatch_due_posts", bind=True)
def dispatch_due_posts(self):
    """
    Runs every minute. Finds all posts with status=SCHEDULED and
    scheduled_at <= now, then enqueues individual publish tasks.
    """
    async def _dispatch():
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
            for post in posts:
                post.status = PostStatus.QUEUED
                db.add(post)
                publish_post.apply_async(args=[str(post.id)], queue="posting")
            await db.commit()
            logger.info(f"Dispatched {len(posts)} posts for publishing.")

    run_async(_dispatch())


@celery_app.task(
    name="app.workers.tasks.posting.publish_post",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def publish_post(self, post_id: str):
    """Publish a single post to its platform."""
    async def _publish():
        async with AsyncSessionLocal() as db:
            post = await db.get(Post, UUID(post_id))
            if not post or post.status not in (PostStatus.QUEUED, PostStatus.FAILED):
                return

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

            # Collect media paths
            media_paths = [m.file_path for m in post.media] if post.media else []

            try:
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
                logger.info(f"Post {post_id} published successfully.")

            except Exception as exc:
                post.retry_count += 1
                post.error_message = str(exc)
                if post.retry_count >= post.max_retries:
                    post.status = PostStatus.FAILED
                    logger.error(f"Post {post_id} failed after {post.retry_count} retries: {exc}")
                else:
                    post.status = PostStatus.SCHEDULED
                    logger.warning(f"Post {post_id} failed, will retry: {exc}")
                    raise self.retry(exc=exc, countdown=60 * post.retry_count)

            await db.commit()

    run_async(_publish())
