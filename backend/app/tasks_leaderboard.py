import datetime
import logging
from celery import shared_task
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.organization import Organization
from app.services.leaderboard_service import LeaderboardService
from app.tasks import _get_redis

logger = logging.getLogger(__name__)

@shared_task(name="app.tasks_leaderboard.generate_monthly_leaderboard_snapshots_task")
def generate_monthly_leaderboard_snapshots_task(organization_id: int = None, period_label: str = None, force: bool = False) -> dict:
    """
    Generates monthly leaderboard snapshots for organizations.
    If period_label is not provided, defaults to the immediately preceding calendar month.
    """
    if not period_label:
        now = datetime.datetime.now(datetime.timezone.utc)
        year = now.year
        month = now.month - 1
        if month == 0:
            month = 12
            year -= 1
        period_label = f"{year}-{month:02d}"
        
    try:
        period_start, period_end = LeaderboardService.period_to_range(period_label)
    except ValueError:
        return {"status": "error", "reason": "Invalid period_label format, expected YYYY-MM"}
        
    db: Session = SessionLocal()
    r = _get_redis()
    
    results = {"success": 0, "skipped": 0, "error": 0}
    
    try:
        if organization_id:
            orgs = [db.query(Organization).filter(Organization.id == organization_id).first()]
        else:
            orgs = db.query(Organization).all()
            
        for org in orgs:
            if not org:
                continue
                
            lock_key = f"lock:leaderboard_snapshot:{org.id}:{period_label}"
            lock = r.lock(lock_key, timeout=600)
            
            if not lock.acquire(blocking=False):
                logger.info(f"Leaderboard snapshot for org {org.id} period {period_label} skipped: lock in use")
                results["skipped"] += 1
                continue
                
            try:
                LeaderboardService.generate_snapshots_for_period(
                    db, org.id, period_label, period_start, period_end, force=force
                )
                results["success"] += 1
            except Exception as e:
                logger.error(f"Failed to generate leaderboard snapshot for org {org.id}: {e}")
                db.rollback()
                results["error"] += 1
            finally:
                try:
                    lock.release()
                except Exception:
                    pass
                    
        # Alert: the beat run is otherwise silent, so a per-org failure would only
        # surface as an empty leaderboard. Log loudly so monitoring can catch it.
        if results["error"] > 0:
            logger.critical(
                f"Leaderboard snapshot generation had {results['error']} org failure(s) "
                f"for period {period_label}: {results}"
            )

        return {"status": "completed", "details": results, "period": period_label}
    finally:
        db.close()
