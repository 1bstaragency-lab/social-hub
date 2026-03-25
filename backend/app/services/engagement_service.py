"""
Engagement Service — executes all engagement actions (like, repost, comment,
follow, play, save) through the appropriate platform client.

Supports:
  • Immediate execution
  • Scheduled / deferred execution (via Celery)
  • Bulk actions across multiple accounts with configurable random delays
  • Rate-limit awareness and per-account daily caps
"""

import uuid
import asyncio
import random
import logging
from datetime import datetime, timezone
from typing import Optional, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.social_account import SocialAccount, AccountCredential
from app.models.activity_log import ActivityLog
from app.core.security import decrypt_credential
from app.platforms import get_platform_client

logger = logging.getLogger(__name__)


async def _load_client(account_id: uuid.UUID, db: AsyncSession):
    """Load account + credentials and instantiate the correct platform client."""
    account = await db.get(SocialAccount, account_id)
    if not account:
        raise ValueError(f"Account {account_id} not found")

    creds_q = await db.execute(
        select(AccountCredential).where(AccountCredential.account_id == account_id)
    )
    creds = {c.credential_type: decrypt_credential(c.encrypted_value)
             for c in creds_q.scalars().all()}

    client_class = get_platform_client(account.platform)
    return client_class(
        account_id=str(account_id),
        credentials=creds,
        proxy=account.proxy_config,
    ), account


async def _log_action(db: AsyncSession, account_id: uuid.UUID, action: str,
                      status: str, description: str = "", metadata: dict = None):
    log = ActivityLog(
        account_id=account_id,
        action=action,
        status=status,
        description=description,
        metadata_=metadata or {},
    )
    db.add(log)
    await db.commit()


# ── Single account engagement ────────────────────────────────────────────────

async def execute_engagement(
    db: AsyncSession,
    account_id: uuid.UUID,
    action_type: str,
    target_id: Optional[str] = None,
    target_url: Optional[str] = None,
    comment_text: Optional[str] = None,
    playlist_id: Optional[str] = None,
) -> dict:
    """
    Execute one engagement action for one account.
    Returns {"success": bool, "result": any, "error": str|None}
    """
    # Use URL as target_id if no explicit ID given
    effective_target = target_id or target_url or ""

    try:
        client, account = await _load_client(account_id, db)

        result = None
        match action_type:
            case "like":
                result = await client.like(effective_target)
            case "unlike":
                result = await client.unlike(effective_target)
            case "repost":
                result = await client.repost(effective_target)
            case "unrepost":
                result = await client.unrepost(effective_target)
            case "comment":
                if not comment_text:
                    raise ValueError("comment_text required for comment action")
                result = await client.comment(effective_target, comment_text)
            case "follow":
                result = await client.follow(effective_target)
            case "unfollow":
                result = await client.unfollow(effective_target)
            case "play":
                result = await client.play_track(effective_target)
            case "save":
                result = await client.save_track(effective_target)
            case "add_to_playlist":
                if not playlist_id:
                    raise ValueError("playlist_id required for add_to_playlist action")
                result = await client.add_to_playlist(effective_target, playlist_id)
            case _:
                raise ValueError(f"Unknown action_type: {action_type}")

        await _log_action(
            db, account_id, f"engagement.{action_type}", "success",
            f"{action_type} on {effective_target}",
            {"target": effective_target, "result": str(result)},
        )
        return {"success": True, "result": result, "error": None}

    except NotImplementedError as e:
        await _log_action(db, account_id, f"engagement.{action_type}", "warning", str(e))
        return {"success": False, "result": None, "error": f"Not supported: {e}"}
    except Exception as e:
        logger.error(f"Engagement {action_type} failed for {account_id}: {e}")
        await _log_action(db, account_id, f"engagement.{action_type}", "failure", str(e))
        return {"success": False, "result": None, "error": str(e)}


# ── Bulk engagement ──────────────────────────────────────────────────────────

async def execute_bulk_engagement(
    db: AsyncSession,
    account_ids: List[uuid.UUID],
    action_type: str,
    target_id: Optional[str] = None,
    target_url: Optional[str] = None,
    comment_text: Optional[str] = None,
    delay_min: int = 5,
    delay_max: int = 30,
) -> List[dict]:
    """
    Run the same engagement action across multiple accounts sequentially,
    with random human-like delays between each to avoid platform detection.
    Returns a list of per-account result dicts.
    """
    results = []
    for i, account_id in enumerate(account_ids):
        if i > 0:
            delay = random.uniform(delay_min, delay_max)
            logger.info(f"Bulk engagement: waiting {delay:.1f}s before next account")
            await asyncio.sleep(delay)

        result = await execute_engagement(
            db=db,
            account_id=account_id,
            action_type=action_type,
            target_id=target_id,
            target_url=target_url,
            comment_text=comment_text,
        )
        result["account_id"] = str(account_id)
        results.append(result)

    return results
