"""
Celery tasks for engagement actions (like, repost, comment, follow, play, save).
Supports immediate, scheduled, and bulk execution.
"""

import asyncio
import random
import logging
from uuid import UUID
from datetime import datetime, timezone
from typing import List, Optional

from app.workers.celery_app import celery_app
from app.core.database import AsyncSessionLocal
from app.services.engagement_service import execute_engagement, execute_bulk_engagement

logger = logging.getLogger(__name__)


def run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(name="app.workers.tasks.engagement.dispatch_due_engagements", bind=True)
def dispatch_due_engagements(self):
    """
    Runs every minute. Dispatches any scheduled engagement actions that are due.
    Engagement actions are stored in the activity_logs table with a 'scheduled' status.
    """
    # Scheduled engagements are dispatched directly via run_engagement_action.apply_async
    # with a countdown; this task is reserved for future DB-driven scheduling.
    pass


@celery_app.task(
    name="app.workers.tasks.engagement.run_engagement_action",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def run_engagement_action(
    self,
    account_id: str,
    action_type: str,
    target_id: Optional[str] = None,
    target_url: Optional[str] = None,
    comment_text: Optional[str] = None,
    playlist_id: Optional[str] = None,
):
    """Execute a single engagement action for one account."""
    async def _run():
        async with AsyncSessionLocal() as db:
            return await execute_engagement(
                db=db,
                account_id=UUID(account_id),
                action_type=action_type,
                target_id=target_id,
                target_url=target_url,
                comment_text=comment_text,
                playlist_id=playlist_id,
            )

    try:
        return run_async(_run())
    except Exception as exc:
        logger.error(f"Engagement task failed: {exc}")
        raise self.retry(exc=exc)


@celery_app.task(
    name="app.workers.tasks.engagement.run_bulk_engagement",
    bind=True,
)
def run_bulk_engagement(
    self,
    account_ids: List[str],
    action_type: str,
    target_id: Optional[str] = None,
    target_url: Optional[str] = None,
    comment_text: Optional[str] = None,
    delay_min: int = 5,
    delay_max: int = 30,
):
    """
    Run the same engagement action across a list of accounts.
    Executes sequentially with randomised delays to mimic organic behaviour.
    """
    async def _run():
        async with AsyncSessionLocal() as db:
            return await execute_bulk_engagement(
                db=db,
                account_ids=[UUID(a) for a in account_ids],
                action_type=action_type,
                target_id=target_id,
                target_url=target_url,
                comment_text=comment_text,
                delay_min=delay_min,
                delay_max=delay_max,
            )

    return run_async(_run())


@celery_app.task(name="app.workers.tasks.engagement.scheduled_engagement_action", bind=True)
def scheduled_engagement_action(self, account_id: str, action_type: str, **kwargs):
    """Thin wrapper used when eta/countdown scheduling is needed."""
    return run_engagement_action.apply(args=[account_id, action_type], kwargs=kwargs).get()
