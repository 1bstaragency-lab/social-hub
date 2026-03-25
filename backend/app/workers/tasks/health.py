"""
Celery task: session health checks every 30 minutes.
Marks accounts as NEEDS_REAUTH if their session/token is invalid.
"""

import asyncio
import logging
from datetime import datetime, timezone

from app.workers.celery_app import celery_app
from app.core.database import AsyncSessionLocal
from app.models.social_account import SocialAccount, AccountCredential, AccountStatus
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


@celery_app.task(name="app.workers.tasks.health.check_all_sessions", bind=True)
def check_all_sessions(self):
    async def _check():
        async with AsyncSessionLocal() as db:
            q = await db.execute(
                select(SocialAccount).where(
                    SocialAccount.status.in_([AccountStatus.ACTIVE, AccountStatus.NEEDS_REAUTH])
                )
            )
            accounts = q.scalars().all()
            logger.info(f"Running health check on {len(accounts)} accounts")

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

                    health = await client.health_check()
                    account.last_health_check = datetime.now(timezone.utc)

                    if health.get("valid"):
                        if account.status == AccountStatus.NEEDS_REAUTH:
                            account.status = AccountStatus.ACTIVE
                    else:
                        account.status = AccountStatus.NEEDS_REAUTH
                        logger.warning(
                            f"Account {account.username} ({account.platform}) "
                            f"needs re-authentication."
                        )

                    db.add(account)

                except Exception as e:
                    logger.error(f"Health check failed for {account.id}: {e}")

            await db.commit()

    run_async(_check())
