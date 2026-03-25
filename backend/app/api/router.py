from fastapi import APIRouter
from app.api.endpoints import accounts, campaigns, posts, engagement, analytics

api_router = APIRouter()
api_router.include_router(accounts.router)
api_router.include_router(campaigns.router)
api_router.include_router(posts.router)
api_router.include_router(engagement.router)
api_router.include_router(analytics.router)
