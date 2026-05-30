from celery import Celery
from celery.schedules import crontab
from app.core.config import settings

celery = Celery(
    "tasks",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    set_as_current=True
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
    }
}

celery.conf.timezone = "UTC"
