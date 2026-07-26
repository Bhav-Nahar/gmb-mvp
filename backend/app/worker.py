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
    broker_heartbeat=300, # Heartbeat every 5 minutes to reduce PING commands
    # Hard/soft task time limits. These MUST stay below the broker
    # visibility_timeout (3600s) below: without them a task that runs longer than
    # the visibility window is redelivered and runs concurrently with itself. The
    # soft limit raises SoftTimeLimitExceeded (catchable for cleanup) ~5 min before
    # the hard kill.
    task_time_limit=1800,       # hard kill at 30 min
    task_soft_time_limit=1500,  # soft (catchable) at 25 min
    # Redis Broker Optimizations for Upstash/Limited Quotas
    broker_transport_options={
        'visibility_timeout': 3600,
        'socket_timeout': 30,
        'socket_connect_timeout': 30,
        'fanout_prefix': True,
        'fanout_patterns': True,
        'polling_interval': 120.0, # Idle maintenance/visibility-scan cadence. Real tasks
                                   # still dispatch instantly (BRPOP wakes on LPUSH); this
                                   # only thins idle polling. Doubled 60->120 to halve the
                                   # residual idle read stream on Upstash's per-command quota.
    },
    broker_pool_limit=5, # Limit concurrent connections
    # Single worker: no peers to gossip/sync with and no need for the remote-control
    # pidbox. The pidbox is a fanout queue the worker polls every loop even when idle —
    # a steady, pointless Redis read source on Upstash. Kill it.
    worker_enable_remote_control=False,
    worker_send_task_events=False,
)

if settings.REDIS_URL.startswith("rediss://"):
    celery.conf.update(
        redis_backend_use_ssl={'ssl_cert_reqs': None},
        broker_use_ssl={'ssl_cert_reqs': None}
    )

# Auto-discover tasks in app.tasks
celery.autodiscover_tasks(["app"])
import app.tasks_leaderboard # Explicitly import to register tasks
import app.tasks_comparison # Explicitly import to register tasks
import app.tasks_reports # Explicitly import to register tasks

# Periodic Celery Beat Scheduling
celery.conf.beat_schedule = {
    "sync-locations-periodic": {
        "task": "app.tasks.sync_all_organizations_task",
        "schedule": 86400.0, # Every 24 hours (86400 seconds) — Google profile/review
                             # data changes slowly; cuts the heavy fan-out cost ~4x vs
                             # the original 6h. Lifecycle transitions are handled
                             # separately by transition-subscriptions below.
    },
    "check-google-updates-weekly": {
        "task": "app.tasks.check_all_google_updates_task",
        "schedule": crontab(day_of_week=1, hour=5, minute=0), # Mondays 5AM UTC. Costs one
                             # extra API call per active location, so it deliberately does
                             # NOT ride the daily sync — Google's own edits are rare and
                             # never urgent, and weekly is ~10x cheaper.
    },
    "transition-subscriptions": {
        "task": "app.tasks.transition_subscriptions_task",
        "schedule": 21600.0, # Every 6 hours — preserves the lifecycle-sweep cadence
                             # previously provided by the (now 12h) location sync, so
                             # trial/grace/expiry transitions are NOT delayed.
    },
    "check-scheduled-posts": {
        "task": "app.tasks.check_scheduled_posts_task",
        "schedule": 300.0, # Every 5 minutes. The task publishes everything with
                           # scheduled_at <= now (oldest-first, batched), so cadence
                           # only sets max publish lag, not correctness. Raised 180->300
                           # to further cut this — the most frequent beat job — in Redis
                           # commands + worker wakeups, at up to ~5 min publish delay.
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
        "schedule": 3600.0, # Every 60 minutes — this only re-enqueues reviews that
                            # failed/were-missed tagging; hourly is ample and 4x cheaper.
    },
    "release-lpseo-index-batch": {
        "task": "app.tasks.release_lpseo_index_batch_task",
        "schedule": 3600.0, # Hourly. Flips local-SEO pages whose drip-feed index_at
                            # has passed. The schedule itself lives in Postgres, so
                            # this tick is one indexed query and usually a no-op —
                            # cadence only sets go-live lag on a plan spanning weeks.
    },
    "reconcile-pending-subscriptions": {
        "task": "app.tasks.reconcile_pending_subscriptions_task",
        "schedule": 1800.0, # Every 30 minutes — safety net for missed payment webhooks.
                            # Happy-path activation is synchronous (webhook + /billing/confirm),
                            # so this fallback can run less often. Worst-case activation
                            # latency for a *missed* webhook rises from ~10m to ~30m.
    },
    "enforce-upi-remandate-grace-daily": {
        "task": "app.tasks.enforce_upi_remandate_grace_task",
        "schedule": crontab(hour=4, minute=0), # Daily at 4AM UTC — re-lock past-grace UPI orgs
    },
    "purge-soft-deleted-accounts": {
        "task": "app.tasks.purge_soft_deleted_accounts_task",
        "schedule": crontab(hour=3, minute=30), # Daily 3:30AM UTC — hard-purge accounts
                            # soft-deleted longer than ACCOUNT_PURGE_GRACE_DAYS (14d).
    },
    "refill-annual-monthly-credits": {
        "task": "app.tasks.refill_annual_monthly_credits_task",
        "schedule": crontab(day_of_month="1", hour=0, minute=30), # 1st of month — annual
                            # subs charge yearly, so this gives them their 12 monthly
                            # credit grants. Monthly subs refill via subscription.charged.
    },
    "generate-monthly-leaderboard-snapshots": {
        "task": "app.tasks_leaderboard.generate_monthly_leaderboard_snapshots_task",
        "schedule": crontab(day_of_month='3', hour=3, minute=0), # Monthly on the 3rd at 3AM UTC —
                            # generates the *previous* month; the 3rd (vs 1st) lets late-arriving
                            # daily-insights/review data settle before the snapshot is taken.
    },
    "aggregate-comparison-insights-daily": {
        "task": "app.tasks_comparison.aggregate_comparison_insights_task",
        "schedule": crontab(hour=2, minute=0), # Daily at 2AM UTC, after sync-insights-daily
    },
    "send-weekly-reports": {
        "task": "app.tasks_reports.send_weekly_reports_task",
        "schedule": crontab(day_of_week="mon", hour=4, minute=0), # Mondays 4AM UTC —
                            # after the daily insights (1AM) + comparison (2AM) jobs have
                            # populated last week's metrics. Reports the prior 7 days.
    }
}

celery.conf.timezone = "UTC"
