from celery import Celery
from celery.schedules import crontab
from app.core.config import settings

celery = Celery(
    "tasks",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    set_as_current=True
)

# Explicitly configure to avoid AMQP fallbacks
celery.conf.update(
    broker_url=settings.REDIS_URL,
    result_backend=settings.REDIS_URL,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    broker_connection_retry_on_startup=True
)

# Auto-discover tasks in app.tasks
celery.autodiscover_tasks(["app"])

# Periodic Celery Beat Scheduling
celery.conf.beat_schedule = {
    "sync-locations-every-hour": {
        "task": "app.tasks.sync_all_organizations_task",
        "schedule": 3600.0, # Every hour (3600 seconds)
    },
    "check-scheduled-posts-every-minute": {
        "task": "app.tasks.check_scheduled_posts_task",
        "schedule": 60.0, # Every minute (60 seconds)
    },
    "archive-activity-logs-daily": {
        "task": "app.tasks.archive_old_activity_logs_task",
        "schedule": crontab(hour=2, minute=0), # Daily at 2AM UTC
    },
    "sync-insights-daily": {
        "task": "app.tasks.sync_all_insights_beat_task",
        "schedule": crontab(hour=1, minute=0), # Daily at 1AM UTC
    },
    "retry-failed-sentiment-hourly": {
        "task": "app.tasks.retry_failed_sentiment_beat_task",
        "schedule": 3600.0, # Every hour
    }
}

celery.conf.timezone = "UTC"
