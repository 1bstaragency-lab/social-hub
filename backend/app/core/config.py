"""
Application configuration using Pydantic settings.
All secrets loaded from environment variables.
"""

from pydantic_settings import BaseSettings
from typing import Optional
from functools import lru_cache


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "SocialHub"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    SECRET_KEY: str = "change-me-in-production"
    API_PREFIX: str = "/api/v1"

    # Database (SQLite for local dev, swap to PostgreSQL for production)
    DATABASE_URL: str = "sqlite+aiosqlite:///./socialhub.db"
    DATABASE_ECHO: bool = False

    # JWT Auth
    JWT_SECRET_KEY: str = "jwt-secret-change-me"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # Encryption (for stored credentials)
    ENCRYPTION_KEY: str = "encryption-key-change-me-32-bytes!"

    # Platform API Keys (optional — used when available)
    TWITTER_API_KEY: Optional[str] = None
    TWITTER_API_SECRET: Optional[str] = None
    SPOTIFY_CLIENT_ID: Optional[str] = None
    SPOTIFY_CLIENT_SECRET: Optional[str] = None

    # Browser Automation
    PLAYWRIGHT_HEADLESS: bool = True
    BROWSER_SESSION_DIR: str = "./browser_sessions"
    MAX_CONCURRENT_BROWSERS: int = 10

    # Rate Limiting
    RATE_LIMIT_DEFAULT: str = "60/minute"

    # File Storage
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE_MB: int = 100

    # Monitoring
    LOG_LEVEL: str = "INFO"
    SENTRY_DSN: Optional[str] = None

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()
