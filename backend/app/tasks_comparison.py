import csv
import json
import logging
import os
from datetime import date, datetime, timedelta
from typing import Optional

from app.worker import celery
from app.db.session import SessionLocal
from app.core.redis_client import get_redis
from app.services.comparison_aggregation_service import ComparisonAggregationService
from app.services.comparison_snapshot_service import ComparisonSnapshotService
from app.services.comparison_cache_service import ComparisonCacheService

logger = logging.getLogger(__name__)

EXPORT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "uploads", "exports")


@celery.task(
    name="app.tasks_comparison.aggregate_comparison_insights_task",
    max_retries=5, autoretry_for=(Exception,), retry_backoff=True,
)
def aggregate_comparison_insights_task(date_str: Optional[str] = None):
    """Aggregate daily group rollups (Region + Custom Group). Defaults to yesterday."""
    target_date = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else date.today() - timedelta(days=1)
    db = SessionLocal()
    try:
        logger.info(f"Starting comparison aggregation for date {target_date}")
        ComparisonAggregationService.aggregate_group_insights(db, target_date)
        ComparisonCacheService.invalidate_comparison_cache()  # org-wide run -> flush all
        logger.info(f"Successfully aggregated comparison insights for {target_date}")
    finally:
        db.close()


@celery.task(
    name="app.tasks_comparison.backfill_comparison_insights_task",
    max_retries=3, autoretry_for=(Exception,), retry_backoff=True,
)
def backfill_comparison_insights_task(start_date_str: str, end_date_str: str, org_id: Optional[int] = None):
    """Backfill historical group insights over a date range (manual trigger)."""
    start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
    end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
    db = SessionLocal()
    try:
        logger.info(f"Backfilling comparison insights {start_date}..{end_date} (org={org_id})")
        ComparisonAggregationService.backfill_group_insights(db, start_date, end_date, org_id)
        ComparisonCacheService.invalidate_comparison_cache(org_id)
        logger.info("Completed comparison backfill")
    finally:
        db.close()


@celery.task(name="app.tasks_comparison.generate_comparison_export_task", max_retries=3)
def generate_comparison_export_task(export_id: str, org_id: int, filters: dict,
                                    allowed_location_ids: Optional[list] = None):
    """Generate a real CSV of the per-group leaderboard for the requested filters.

    allowed_location_ids re-applies the caller's location scope inside the worker so a
    restricted user can't export org-wide data via a hijacked export id.
    """
    redis_client = get_redis()
    db = SessionLocal()
    try:
        rows = ComparisonSnapshotService.get_leaderboard(db, org_id, filters, allowed_location_ids)
        os.makedirs(EXPORT_DIR, exist_ok=True)
        path = os.path.join(EXPORT_DIR, f"{export_id}.csv")
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["group", "score"])
            for r in rows:
                w.writerow([r["name"], r["score"]])

        if redis_client:
            redis_client.setex(f"export:{export_id}", 86400, json.dumps({
                "status": "completed",
                "download_url": f"/static/uploads/exports/{export_id}.csv",
                "org_id": org_id,
            }))
        logger.info(f"Comparison export {export_id} completed ({len(rows)} rows)")
    except Exception as e:
        if redis_client:
            redis_client.setex(f"export:{export_id}", 86400, json.dumps({
                "status": "failed", "download_url": None, "org_id": org_id,
            }))
        logger.error(f"Comparison export {export_id} failed: {e}")
        raise
    finally:
        db.close()
