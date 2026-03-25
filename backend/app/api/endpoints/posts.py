"""
API endpoints for post management (create, schedule, cross-post, list).
"""

from uuid import UUID, uuid4
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.core.database import get_db
from app.models.post import Post, PostMedia, PostStatus, PostType
from app.schemas.post import PostCreate, PostUpdate, PostOut

router = APIRouter(prefix="/posts", tags=["Posts"])


@router.get("/", response_model=List[PostOut])
async def list_posts(
    account_id: Optional[UUID] = Query(None),
    campaign_id: Optional[UUID] = Query(None),
    status: Optional[PostStatus] = Query(None),
    scheduled_after: Optional[datetime] = Query(None),
    scheduled_before: Optional[datetime] = Query(None),
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    q = select(Post)
    if account_id:
        q = q.where(Post.account_id == account_id)
    if campaign_id:
        q = q.where(Post.campaign_id == campaign_id)
    if status:
        q = q.where(Post.status == status)
    if scheduled_after:
        q = q.where(Post.scheduled_at >= scheduled_after)
    if scheduled_before:
        q = q.where(Post.scheduled_at <= scheduled_before)
    q = q.order_by(Post.scheduled_at.asc()).offset(skip).limit(limit)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/", response_model=PostOut, status_code=status.HTTP_201_CREATED)
async def create_post(payload: PostCreate, db: AsyncSession = Depends(get_db)):
    """Create a post (draft or scheduled). Set scheduled_at to publish at a specific time."""
    post_status = PostStatus.SCHEDULED if payload.scheduled_at else PostStatus.DRAFT

    post = Post(
        account_id=payload.account_id,
        campaign_id=payload.campaign_id,
        cross_post_group_id=payload.cross_post_group_id,
        post_type=payload.post_type,
        status=post_status,
        content_text=payload.content_text,
        content_metadata=payload.content_metadata or {},
        scheduled_at=payload.scheduled_at,
    )
    db.add(post)
    await db.flush()

    for i, media in enumerate(payload.media or []):
        db.add(PostMedia(
            post_id=post.id,
            media_type=media.media_type,
            file_path=media.file_path,
            mime_type=media.mime_type,
            sort_order=i,
        ))

    await db.commit()
    await db.refresh(post)
    return post


@router.post("/cross-post", response_model=List[PostOut], status_code=status.HTTP_201_CREATED)
async def cross_post(
    payloads: List[PostCreate],
    db: AsyncSession = Depends(get_db),
):
    """
    Create the same content across multiple accounts/platforms in one call.
    All posts share the same cross_post_group_id for reporting.
    """
    group_id = uuid4()
    posts = []
    for payload in payloads:
        payload.cross_post_group_id = group_id
        post_status = PostStatus.SCHEDULED if payload.scheduled_at else PostStatus.DRAFT
        post = Post(
            account_id=payload.account_id,
            campaign_id=payload.campaign_id,
            cross_post_group_id=group_id,
            post_type=payload.post_type,
            status=post_status,
            content_text=payload.content_text,
            content_metadata=payload.content_metadata or {},
            scheduled_at=payload.scheduled_at,
        )
        db.add(post)
        await db.flush()
        for i, media in enumerate(payload.media or []):
            db.add(PostMedia(
                post_id=post.id,
                media_type=media.media_type,
                file_path=media.file_path,
                mime_type=media.mime_type,
                sort_order=i,
            ))
        posts.append(post)

    await db.commit()
    for p in posts:
        await db.refresh(p)
    return posts


@router.get("/{post_id}", response_model=PostOut)
async def get_post(post_id: UUID, db: AsyncSession = Depends(get_db)):
    post = await db.get(Post, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return post


@router.patch("/{post_id}", response_model=PostOut)
async def update_post(post_id: UUID, payload: PostUpdate, db: AsyncSession = Depends(get_db)):
    post = await db.get(Post, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    if post.status == PostStatus.PUBLISHED:
        raise HTTPException(status_code=400, detail="Cannot edit a published post")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(post, field, value)
    db.add(post)
    await db.commit()
    await db.refresh(post)
    return post


@router.post("/{post_id}/publish-now", response_model=PostOut)
async def publish_now(post_id: UUID, db: AsyncSession = Depends(get_db)):
    """Immediately publish a draft post (bypasses scheduler)."""
    post = await db.get(Post, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    if post.status == PostStatus.PUBLISHED:
        raise HTTPException(status_code=400, detail="Post already published")
    # Mark as scheduled so the in-process scheduler picks it up within 30 seconds
    from datetime import datetime, timezone
    post.status = PostStatus.SCHEDULED
    post.scheduled_at = datetime.now(timezone.utc)
    db.add(post)
    await db.commit()
    await db.refresh(post)
    return post


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(post_id: UUID, db: AsyncSession = Depends(get_db)):
    post = await db.get(Post, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    if post.status == PostStatus.PUBLISHING:
        raise HTTPException(status_code=400, detail="Cannot delete a post that is currently publishing")
    await db.delete(post)
    await db.commit()
