"""
API endpoints for SoundCloud browser-based authentication.

Since SoundCloud's developer portal is private (no new app registrations),
we authenticate via Playwright browser automation instead of OAuth.

Endpoints:
  POST /api/v1/soundcloud/login     - Browser login with email/password
  POST /api/v1/soundcloud/validate  - Validate stored session
  POST /api/v1/soundcloud/relogin   - Re-authenticate with stored credentials
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import encrypt_value, decrypt_value
from app.db.session import get_db
from app.models.social_account import (
    SocialAccount,
    AccountCredential,
    Platform,
    AccountStatus,
    AuthMethod,
)
from app.services.soundcloud_auth import SoundCloudAuthService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/soundcloud", tags=["soundcloud-auth"])


# ── Request / Response Models ─────────────────────────────────────────────────


class SCLoginRequest(BaseModel):
    email: str
    password: str
    account_id: Optional[str] = None
    proxy: Optional[dict] = None


class SCLoginResponse(BaseModel):
    success: bool
    account_id: str
    username: str
    display_name: str
    avatar_url: str
    follower_count: int = 0
    following_count: int = 0
    track_count: int = 0
    has_oauth_token: bool = False
    message: str = ""


class SCValidateRequest(BaseModel):
    account_id: str


class SCValidateResponse(BaseModel):
    valid: bool
    needs_relogin: bool = False
    profile: Optional[dict] = None
    error: Optional[str] = None


# ── POST /api/v1/soundcloud/login ─────────────────────────────────────────────


@router.post("/login", response_model=SCLoginResponse)
async def soundcloud_login(req: SCLoginRequest, db: AsyncSession = Depends(get_db)):
    """
    Log into SoundCloud via Playwright browser automation.
    Captures OAuth token + cookies, stores encrypted credentials,
    and populates account profile data.
    """
    auth_svc = SoundCloudAuthService(
        account_id=req.account_id or "new",
        proxy=req.proxy,
    )

    try:
        result = await auth_svc.login(req.email, req.password)
    except Exception as e:
        logger.error(f"SoundCloud login failed: {e}")
        raise HTTPException(status_code=401, detail=f"Login failed: {str(e)}")
    finally:
        await auth_svc.close()

    if not result.get("logged_in"):
        raise HTTPException(status_code=401, detail="Login failed")

    profile = result.get("profile") or {}

    # ── Upsert the SocialAccount ──────────────────────────────────────────
    if req.account_id:
        account = await db.get(SocialAccount, req.account_id)
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")
    else:
        username = profile.get("username", "")
        from sqlalchemy import select

        stmt = select(SocialAccount).where(
            SocialAccount.platform == Platform.SOUNDCLOUD,
            SocialAccount.username == username,
        )
        existing = (await db.execute(stmt)).scalar_one_or_none()
        if existing:
            account = existing
        else:
            account = SocialAccount(
                platform=Platform.SOUNDCLOUD,
                username=username,
            )
            db.add(account)

    # Update account fields from profile
    account.username = profile.get("username", account.username or "")
    account.display_name = profile.get("display_name", "")
    account.avatar_url = profile.get("avatar_url", "")
    account.bio = profile.get("bio", "")
    account.follower_count = profile.get("follower_count", 0)
    account.following_count = profile.get("following_count", 0)
    account.track_count = profile.get("track_count", 0)
    account.platform_user_id = profile.get("platform_user_id", "")
    account.profile_url = profile.get("profile_url", "")
    account.is_verified = profile.get("is_verified", False)
    account.status = AccountStatus.ACTIVE
    account.auth_method = AuthMethod.BROWSER_SESSION

    await db.flush()

    # ── Store encrypted credentials ───────────────────────────────────────
    from sqlalchemy import delete

    await db.execute(
        delete(AccountCredential).where(AccountCredential.account_id == account.id)
    )

    db.add(AccountCredential(
        account_id=account.id,
        credential_type="email",
        encrypted_value=encrypt_value(req.email),
    ))
    db.add(AccountCredential(
        account_id=account.id,
        credential_type="password",
        encrypted_value=encrypt_value(req.password),
    ))
    if result.get("oauth_token"):
        db.add(AccountCredential(
            account_id=account.id,
            credential_type="access_token",
            encrypted_value=encrypt_value(result["oauth_token"]),
        ))
    if result.get("client_id"):
        db.add(AccountCredential(
            account_id=account.id,
            credential_type="api_key",
            encrypted_value=encrypt_value(result["client_id"]),
        ))
    if result.get("cookies"):
        db.add(AccountCredential(
            account_id=account.id,
            credential_type="session_cookies",
            encrypted_value=encrypt_value(result["cookies"]),
        ))

    await db.commit()
    await db.refresh(account)

    return SCLoginResponse(
        success=True,
        account_id=str(account.id),
        username=account.username,
        display_name=account.display_name or "",
        avatar_url=account.avatar_url or "",
        follower_count=account.follower_count or 0,
        following_count=account.following_count or 0,
        track_count=getattr(account, "track_count", 0),
        has_oauth_token=bool(result.get("oauth_token")),
        message="Logged in via browser session"
        + (" (session-only)" if not result.get("oauth_token") else ""),
    )


# ── POST /api/v1/soundcloud/validate ──────────────────────────────────────────


@router.post("/validate", response_model=SCValidateResponse)
async def soundcloud_validate(req: SCValidateRequest, db: AsyncSession = Depends(get_db)):
    """Validate a stored SoundCloud browser session."""
    account = await db.get(SocialAccount, req.account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    auth_svc = SoundCloudAuthService(account_id=str(account.id))

    try:
        result = await auth_svc.validate_session()
    except Exception as e:
        logger.error(f"Session validation error: {e}")
        return SCValidateResponse(valid=False, needs_relogin=True, error=str(e))
    finally:
        await auth_svc.close()

    if result.get("valid") and result.get("profile"):
        profile = result["profile"]
        account.follower_count = profile.get("follower_count", account.follower_count)
        account.following_count = profile.get("following_count", account.following_count)
        account.track_count = profile.get("track_count", getattr(account, "track_count", 0))
        account.display_name = profile.get("display_name", account.display_name)
        account.avatar_url = profile.get("avatar_url", account.avatar_url)
        await db.commit()

    if result.get("needs_relogin"):
        account.status = AccountStatus.NEEDS_REAUTH
        await db.commit()

    return SCValidateResponse(
        valid=result.get("valid", False),
        needs_relogin=result.get("needs_relogin", False),
        profile=result.get("profile"),
        error=result.get("error"),
    )


# ── POST /api/v1/soundcloud/relogin ──────────────────────────────────────────


@router.post("/relogin", response_model=SCLoginResponse)
async def soundcloud_relogin(req: SCValidateRequest, db: AsyncSession = Depends(get_db)):
    """Re-authenticate using stored credentials (auto re-login on session expiry)."""
    account = await db.get(SocialAccount, req.account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    from sqlalchemy import select

    creds_stmt = select(AccountCredential).where(
        AccountCredential.account_id == account.id
    )
    creds_result = await db.execute(creds_stmt)
    creds = {c.credential_type: decrypt_value(c.encrypted_value) for c in creds_result.scalars()}

    if "email" not in creds or "password" not in creds:
        raise HTTPException(
            status_code=400,
            detail="No stored email/password — manual re-login required",
        )

    return await soundcloud_login(
        SCLoginRequest(
            email=creds["email"],
            password=creds["password"],
            account_id=str(account.id),
        ),
        db=db,
    )
