"""
API endpoints for social account management.
"""

from uuid import UUID
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import encrypt_credential
from app.models.social_account import SocialAccount, AccountCredential, AccountStatus, Platform
from app.schemas.social_account import (
    SocialAccountCreate, SocialAccountUpdate, SocialAccountOut, AccountHealthStatus
)
router = APIRouter(prefix="/accounts", tags=["Accounts"])


@router.get("/", response_model=List[SocialAccountOut])
async def list_accounts(
    organization_id: Optional[UUID] = Query(None),
    platform: Optional[Platform] = Query(None),
    status: Optional[AccountStatus] = Query(None),
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    """List all social accounts, optionally filtered by org, platform, or status."""
    q = select(SocialAccount)
    if organization_id:
        q = q.where(SocialAccount.organization_id == organization_id)
    if platform:
        q = q.where(SocialAccount.platform == platform)
    if status:
        q = q.where(SocialAccount.status == status)
    q = q.offset(skip).limit(limit)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/", response_model=SocialAccountOut, status_code=status.HTTP_201_CREATED)
async def create_account(
    payload: SocialAccountCreate,
    db: AsyncSession = Depends(get_db),
):
    """Register a new social account and store its credentials (encrypted)."""
    account = SocialAccount(
        organization_id=payload.organization_id,
        platform=payload.platform,
        username=payload.username,
        display_name=payload.display_name,
        avatar_url=payload.avatar_url,
        auth_method=payload.auth_method,
        proxy_config=payload.proxy_config,
        rate_limit_config=payload.rate_limit_config,
    )
    db.add(account)
    await db.flush()  # Get account.id before adding credentials

    # Encrypt and store each credential
    for cred_type, cred_value in payload.credentials.items():
        cred = AccountCredential(
            account_id=account.id,
            credential_type=cred_type,
            encrypted_value=encrypt_credential(cred_value),
        )
        db.add(cred)

    await db.commit()
    await db.refresh(account)
    return account


@router.get("/{account_id}", response_model=SocialAccountOut)
async def get_account(account_id: UUID, db: AsyncSession = Depends(get_db)):
    account = await db.get(SocialAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return account


@router.patch("/{account_id}", response_model=SocialAccountOut)
async def update_account(
    account_id: UUID,
    payload: SocialAccountUpdate,
    db: AsyncSession = Depends(get_db),
):
    account = await db.get(SocialAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(account, field, value)
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return account


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(account_id: UUID, db: AsyncSession = Depends(get_db)):
    account = await db.get(SocialAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    await db.delete(account)
    await db.commit()


@router.post("/{account_id}/credentials", status_code=status.HTTP_204_NO_CONTENT)
async def update_credentials(
    account_id: UUID,
    credentials: dict,
    db: AsyncSession = Depends(get_db),
):
    """Update or replace credentials for an account (e.g. after re-auth)."""
    account = await db.get(SocialAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    for cred_type, cred_value in credentials.items():
        q = await db.execute(
            select(AccountCredential).where(
                AccountCredential.account_id == account_id,
                AccountCredential.credential_type == cred_type,
            )
        )
        existing = q.scalar_one_or_none()
        if existing:
            existing.encrypted_value = encrypt_credential(cred_value)
            db.add(existing)
        else:
            db.add(AccountCredential(
                account_id=account_id,
                credential_type=cred_type,
                encrypted_value=encrypt_credential(cred_value),
            ))

    account.status = AccountStatus.ACTIVE
    db.add(account)
    await db.commit()


@router.post("/{account_id}/health-check", response_model=AccountHealthStatus)
async def health_check_account(account_id: UUID, db: AsyncSession = Depends(get_db)):
    """Trigger an immediate health check on one account."""
    from datetime import datetime, timezone
    from app.models.social_account import AccountCredential
    from app.core.security import decrypt_credential
    from app.platforms import get_platform_client

    account = await db.get(SocialAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    creds_q = await db.execute(
        select(AccountCredential).where(AccountCredential.account_id == account_id)
    )
    creds = {c.credential_type: decrypt_credential(c.encrypted_value)
             for c in creds_q.scalars().all()}

    client_class = get_platform_client(account.platform)
    client = client_class(account_id=str(account_id), credentials=creds,
                          proxy=account.proxy_config)
    health = await client.health_check()

    account.last_health_check = datetime.now(timezone.utc)
    if not health.get("valid"):
        account.status = AccountStatus.NEEDS_REAUTH
    db.add(account)
    await db.commit()

    return AccountHealthStatus(
        account_id=account_id,
        platform=account.platform,
        username=account.username,
        status=account.status,
        session_valid=health.get("valid", False),
        last_checked=account.last_health_check,
        error=health.get("error"),
    )


@router.post("/health-check/all")
async def health_check_all():
    """Health checks run automatically every 30 minutes via the in-process scheduler."""
    return {"message": "Health checks run automatically every 30 minutes. Next check is scheduled."}
