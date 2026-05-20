from celery import Celery
from celery.schedules import crontab
from app.core.config import settings

celery = Celery(
    "tasks",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL
)

# Auto-discover tasks in app.tasks
celery.autodiscover_tasks(["app"])

# Periodic Celery Beat Scheduling
celery.conf.beat_schedule = {
    "sync-locations-every-hour": {
        "task": "app.tasks.sync_all_organizations_task",
        "schedule": 3600.0, # Every hour (3600 seconds)
    }
}

celery.conf.timezone = "UTC"
