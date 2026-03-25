"""
Celery application — background task queue for:
  • Scheduled post publishing
  • Scheduled engagement actions (like, follow, play, comment, repost)
  • Bulk engagement campaigns
  • Analytics collection (hourly/daily snapshots)
  • Session health checks
"""

from celery import Celery
from celery.schedules import crontab
from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "socialhub",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.workers.tasks.posting",
        "app.workers.tasks.engagement",
        "app.workers.tasks.analytics",
        "app.workers.tasks.health",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,          # Only ack after task completes (retry on crash)
    worker_prefetch_multiplier=1,  # Prevent a single worker from hoarding tasks
    task_routes={
        "app.workers.tasks.posting.*":    {"queue": "posting"},
        "app.workers.tasks.engagement.*": {"queue": "engagement"},
        "app.workers.tasks.analytics.*":  {"queue": "analytics"},
        "app.workers.tasks.health.*":     {"queue": "health"},
    },
    beat_schedule={
        # Pick up scheduled posts every minute
        "dispatch-scheduled-posts": {
            "task": "app.workers.tasks.posting.dispatch_due_posts",
            "schedule": crontab(minute="*"),
        },
        # Dispatch scheduled engagement actions every minute
        "dispatch-scheduled-engagements": {
            "task": "app.workers.tasks.engagement.dispatch_due_engagements",
            "schedule": crontab(minute="*"),
        },
        # Hourly analytics snapshots
        "collect-hourly-analytics": {
            "task": "app.workers.tasks.analytics.collect_snapshots",
            "schedule": crontab(minute=0),
            "kwargs": {"interval": "hourly"},
        },
        # Daily analytics snapshots at midnight UTC
        "collect-daily-analytics": {
            "task": "app.workers.tasks.analytics.collect_snapshots",
            "schedule": crontab(hour=0, minute=0),
            "kwargs": {"interval": "daily"},
        },
        # Session health check every 30 minutes
        "health-check-sessions": {
            "task": "app.workers.tasks.health.check_all_sessions",
            "schedule": crontab(minute="*/30"),
        },
    },
)
