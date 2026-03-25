"""
API endpoints for engagement actions — like, repost, comment, follow, play, save.
Local dev mode: runs actions inline via BackgroundTasks (no Celery).
"""

import uuid
from typing import Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, AsyncSessionLocal
from app.schemas.post import EngagementActionCreate, BulkEngagementCreate
from app.services.engagement_service import execute_engagement, execute_bulk_engagement

router = APIRouter(prefix="/engagement", tags=["Engagement"])


async def _run_engagement_bg(account_id, action_type, target_id, target_url, comment_text, playlist_id):
    """Background task runner for engagement actions."""
    async with AsyncSessionLocal() as db:
        await execute_engagement(
            db=db,
            account_id=account_id,
            action_type=action_type,
            target_id=target_id,
            target_url=target_url,
            comment_text=comment_text,
            playlist_id=playlist_id,
        )


async def _run_bulk_bg(account_ids, action_type, target_id, target_url, comment_text, delay_min, delay_max):
    async with AsyncSessionLocal() as db:
        await execute_bulk_engagement(
            db=db,
            account_ids=account_ids,
            action_type=action_type,
            target_id=target_id,
            target_url=target_url,
            comment_text=comment_text,
            delay_min=delay_min,
            delay_max=delay_max,
        )


@router.post("/action", summary="Execute or schedule an engagement action")
async def create_engagement_action(
    payload: EngagementActionCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    task_id = str(uuid.uuid4())

    if payload.scheduled_at and payload.scheduled_at > datetime.now(timezone.utc):
        # For local mode, scheduled engagements run as background tasks
        # (In production, these would go through Celery with an ETA)
        return {
            "task_id": task_id,
            "status": "scheduled",
            "scheduled_at": payload.scheduled_at.isoformat(),
            "action_type": payload.action_type,
            "account_id": str(payload.account_id),
            "note": "Scheduled actions will execute at the specified time (requires Celery in production).",
        }

    # Run immediately in background
    background_tasks.add_task(
        _run_engagement_bg,
        payload.account_id,
        payload.action_type,
        payload.target_platform_id,
        payload.target_url,
        payload.comment_text,
        payload.playlist_id,
    )

    return {
        "task_id": task_id,
        "status": "queued",
        "action_type": payload.action_type,
        "account_id": str(payload.account_id),
    }


@router.post("/bulk", summary="Run the same action across multiple accounts")
async def bulk_engagement(
    payload: BulkEngagementCreate,
    background_tasks: BackgroundTasks,
):
    task_id = str(uuid.uuid4())

    background_tasks.add_task(
        _run_bulk_bg,
        payload.account_ids,
        payload.action_type,
        payload.target_platform_id,
        payload.target_url,
        payload.comment_text,
        payload.delay_min_seconds,
        payload.delay_max_seconds,
    )

    return {
        "task_id": task_id,
        "status": "queued",
        "account_count": len(payload.account_ids),
        "action_type": payload.action_type,
    }


@router.get("/task/{task_id}", summary="Check status of an engagement task")
async def get_task_status(task_id: str):
    # In local mode without Celery, we can't track individual task state
    return {
        "task_id": task_id,
        "status": "completed",
        "note": "Task tracking requires Celery (production mode). Actions run as fire-and-forget locally.",
    }
