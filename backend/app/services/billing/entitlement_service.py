from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
import redis
from app.models.organization import Organization
from app.core.config import settings

def get_redis_client() -> redis.Redis:
    return redis.from_url(settings.REDIS_URL, decode_responses=True)

class EntitlementService:
    """Service to handle organization locks and trial/subscription lifecycle transitions."""

    @staticmethod
    def is_org_locked(org: Organization) -> bool:
        """
        Check if an organization is locked from writing or using AI/platform features.
        """
        now = datetime.now(timezone.utc)

        if org.subscription_status == "locked":
            return True

        # Trial pending activation is technically not locked, but limited
        if org.subscription_status == "trial_pending_activation":
            return False

        if org.subscription_status == "past_due":
            if org.grace_period_ends_at and org.grace_period_ends_at > now:
                return False  # Still in grace period
            return True

        if org.subscription_status == "cancelled_active":
            if org.subscription_ends_at and org.subscription_ends_at < now:
                return True
            return False

        if org.subscription_status == "trial":
            if org.trial_ends_at and org.trial_ends_at < now:
                return True # Should have been transitioned, but treat as locked if past
            return False

        # Active
        return False

    @staticmethod
    def transition_expired_subscriptions(db: Session) -> None:
        """
        Scan and transition expired trials and subscriptions.
        Uses a Redis lock to ensure only one worker executes this at a time.
        """
        redis_client = get_redis_client()
        lock = redis_client.lock("lock:transition_expired_subscriptions", timeout=300)
        
        if not lock.acquire(blocking=False):
            return  # Another worker is already processing this

        try:
            now = datetime.now(timezone.utc)
            
            # Step 1: Trial -> Past Due (Grace Period)
            trials_to_past_due = db.query(Organization).filter(
                Organization.subscription_status == "trial",
                Organization.trial_ends_at < now
            ).all()

            for org in trials_to_past_due:
                org.subscription_status = "past_due"
                org.grace_period_ends_at = now + timedelta(days=3)
            
            # Step 2: Past Due -> Locked
            past_due_to_locked = db.query(Organization).filter(
                Organization.subscription_status == "past_due",
                Organization.grace_period_ends_at < now
            ).all()

            for org in past_due_to_locked:
                org.subscription_status = "locked"

            # Step 3: Cancelled Active -> Locked
            cancelled_to_locked = db.query(Organization).filter(
                Organization.subscription_status == "cancelled_active",
                Organization.subscription_ends_at < now
            ).all()

            for org in cancelled_to_locked:
                org.subscription_status = "locked"

            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            lock.release()
