"""
SocialHub — FastAPI application entry point.
Local dev mode: SQLite + APScheduler (no Docker/Postgres/Redis/Celery needed).
"""

import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.database import create_all_tables
from app.api.router import api_router

settings = get_settings()
logging.basicConfig(level=settings.LOG_LEVEL)
logger = logging.getLogger(__name__)


async def seed_default_org():
    """Create a default organization if none exists."""
    from app.core.database import AsyncSessionLocal
    from app.models.organization import Organization
    from sqlalchemy import select
    import uuid

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Organization).limit(1))
        if not result.scalar_one_or_none():
            org = Organization(
                id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
                name="Default",
                slug="default",
                description="Default organization",
            )
            db.add(org)
            await db.commit()
            logger.info("Created default organization.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown events."""
    os.makedirs(settings.BROWSER_SESSION_DIR, exist_ok=True)
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

    # Create all tables (local dev — no Alembic needed)
    import app.models  # noqa: F401 — register all models
    await create_all_tables()
    logger.info("Database tables created/verified.")

    await seed_default_org()

    # Start in-process scheduler for post dispatch + health checks
    from app.workers.scheduler import start_scheduler, stop_scheduler
    start_scheduler()
    logger.info("In-process scheduler started.")

    yield

    stop_scheduler()
    logger.info("Scheduler stopped.")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Mass social media account management across SoundCloud, TikTok, Twitter/X, and Spotify.",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    lifespan=lifespan,
)

# CORS — allow the React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount all API routes under /api/v1
app.include_router(api_router, prefix=settings.API_PREFIX)


@app.get("/health")
async def health():
    return {"status": "ok", "version": settings.APP_VERSION}
