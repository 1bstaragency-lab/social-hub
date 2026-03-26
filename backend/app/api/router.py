from fastapi import APIRouter

from app.api.endpoints import accounts, campaigns, posts, engagement, analytics
from app.api.endpoints.soundcloud_auth import router as sc_auth_router

api_router = APIRouter()

api_router.include_router(accounts.router)
api_router.include_router(campaigns.router)
api_router.include_router(posts.router)
api_router.include_router(engagement.router)
api_router.include_router(analytics.router)

# SoundCloud browser-based auth (login/validate/relogin)
api_router.include_router(sc_auth_router)
