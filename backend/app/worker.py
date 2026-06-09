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
    result_backend=None, # Disable result backend to save massive amounts of Redis requests
    task_ignore_result=True, # Don't store task results
    task_store_errors_even_if_ignored=True,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
    broker_heartbeat=120, # Decrease heartbeat frequency to reduce PING commands
    # Redis Broker Optimizations for Upstash/Limited Quotas
    broker_transport_options={
        'visibility_timeout': 3600,
        'socket_timeout': 30,
        'socket_connect_timeout': 30,
        'fanout_prefix': True,
        'fanout_patterns': True,
        'polling_interval': 10.0, # Poll Redis every 10 seconds instead of continuously
    },
    broker_pool_limit=10, # Limit concurrent connections
)

# Auto-discover tasks in app.tasks
celery.autodiscover_tasks(["app"])

# Periodic Celery Beat Scheduling
celery.conf.beat_schedule = {
    "sync-locations-every-hour": {
        "task": "app.tasks.sync_all_organizations_task",
        "schedule": 21600.0, # Every 6 hours (21600 seconds)
    },
    "check-scheduled-posts-every-minute": {
        "task": "app.tasks.check_scheduled_posts_task",
        "schedule": 300.0, # Every 5 minutes (300 seconds)
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
        "schedule": 900.0, # Every 15 minutes (900 seconds)
    }
}

celery.conf.timezone = "UTC"
