import datetime
from datetime import timezone
from celery import shared_task
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.user import User
from app.models.organization import Organization
from app.models.oauth_account import OAuthAccount
from app.models.location import Location
from app.models.sync_log import SyncLog
from app.core.security import decrypt_token, encrypt_token
from app.providers.factory import ProviderFactory
from app.providers.base.exceptions import ProviderAuthError
from app.services.review_sync_service import ReviewSyncService
import asyncio

@shared_task(name="app.tasks.sync_reviews_task")
def sync_reviews_task(location_id: int, run_type: str = "Scheduled", user_id: int = None) -> dict:
    """
    Synchronizes reviews for a specific location via the ReviewSyncService.
    """
    import redis
    from app.core.config import settings
    
    db: Session = SessionLocal()
    try:
        location = db.query(Location).filter(Location.id == location_id).first()
        if not location:
            return {"status": "error", "reason": f"Location {location_id} not found"}
            
        if user_id:
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                from app.api.deps import get_user_location_ids
                allowed_location_ids = get_user_location_ids(user, db)
                if allowed_location_ids is not None and location_id not in allowed_location_ids:
                    return {"status": "error", "reason": "User does not have permission for this location"}
        
        organization_id = location.organization_id
        
        r = redis.Redis.from_url(settings.REDIS_URL)
        lock_key = f"lock:sync_reviews:{organization_id}:{location_id}"
        lock = r.lock(lock_key, timeout=300)
        
        if not lock.acquire(blocking=False):
            return {"status": "skipped", "reason": "sync already in progress"}
            
        try:
            sync_log = SyncLog(
                organization_id=organization_id,
                location_id=location_id,
                status="Pending",
                run_type=run_type,
                error_message=None
            )
            db.add(sync_log)
            db.commit()
            db.refresh(sync_log)
            
            result = asyncio.run(ReviewSyncService.sync_location_reviews(db, location_id, run_type, sync_log_id=sync_log.id))

            # Fire-and-forget: enqueue sentiment tagging after a successful sync.
            # Only fires on success — never on failure.
            tag_reviews_sentiment_task.delay(
                location_id=location_id,
                organization_id=organization_id
            )

            return {"status": "success", "result": result}
        except Exception as e:
            db.rollback()
            db.query(SyncLog).filter(SyncLog.id == sync_log.id).update({
                SyncLog.status: "Failed",
                SyncLog.error_message: f"Sync Failed: {str(e)}"
            })
            db.commit()
            raise e
        finally:
            try:
                lock.release()
            except Exception:
                pass
    finally:
        db.close()

@shared_task(name="app.tasks.sync_locations_task")
def sync_locations_task(organization_id: int, user_id: int, run_type: str = "Scheduled") -> dict:
    """
    Synchronizes Google Business Profile locations for an organization
    using the user's encrypted tokens fetched from the oauth_accounts table.
    Gracefully handles token refreshing and encryption/decryption cycles.
    """
    import redis
    from app.core.config import settings
    
    db: Session = SessionLocal()
    
    r = redis.Redis.from_url(settings.REDIS_URL)
    lock_key = f"lock:sync_all:{organization_id}"
    lock = r.lock(lock_key, timeout=300)
    
    if not lock.acquire(blocking=False):
        db.close()
        return {"status": "skipped", "reason": "sync already in progress"}
    
    try:
        sync_log = SyncLog(
            organization_id=organization_id,
            status="Pending",
            run_type=run_type,
            error_message=None
        )
        db.add(sync_log)
        db.commit()
        db.refresh(sync_log)
        
        provider = ProviderFactory.get_provider("gbp", organization_id, db)
        provider_locations = asyncio.run(provider.get_locations())
        
        synced_count = 0
        sync_jobs = []
        for p_loc in provider_locations:
            print(f"DEBUG: Processing location: {p_loc.name}")
            
            # Check if location already exists in db
            existing_loc = db.query(Location).filter(
                Location.organization_id == organization_id,
                Location.google_location_id == p_loc.provider_location_id
            ).first()
            
            if existing_loc:
                # Update
                existing_loc.google_account_id = p_loc.google_account_id
                existing_loc.location_name = p_loc.name
                existing_loc.primary_category = p_loc.category
                existing_loc.address = p_loc.address
                existing_loc.phone = p_loc.phone
                existing_loc.website = p_loc.website
                existing_loc.average_rating = p_loc.average_rating
                existing_loc.total_reviews = p_loc.total_reviews
                existing_loc.sync_status = "Synced"
                existing_loc.last_synced_at = datetime.datetime.utcnow()
                db.flush()
                loc_id = existing_loc.id
            else:
                # Insert new
                new_loc = Location(
                    organization_id=organization_id,
                    google_account_id=p_loc.google_account_id,
                    google_location_id=p_loc.provider_location_id,
                    location_name=p_loc.name,
                    primary_category=p_loc.category,
                    address=p_loc.address,
                    phone=p_loc.phone,
                    website=p_loc.website,
                    average_rating=p_loc.average_rating,
                    total_reviews=p_loc.total_reviews,
                    sync_status="Synced",
                    last_synced_at=datetime.datetime.utcnow()
                )
                db.add(new_loc)
                db.flush()
                loc_id = new_loc.id
                
            sync_jobs.append(loc_id)
            synced_count += 1
            
        # Commit once after the loop
        db.commit()
        
        # Trigger review sync for this location
        for loc_id in sync_jobs:
            sync_reviews_task.delay(loc_id, run_type, user_id)
            
        # Log successful sync operation
        log_message = f"Synchronized {synced_count} locations successfully."
        sync_log.status = "Success"
        sync_log.error_message = log_message
        db.commit()
        
        return {"status": "success", "result": log_message}

    except Exception as e:
        db.rollback()
        
        # If refreshing has failed catastrophically
        if isinstance(e, ProviderAuthError) or "re-authentication required" in str(e).lower() or "invalid_grant" in str(e).lower():
            # Find and delete oauth account securely
            oauth_account = db.query(OAuthAccount).join(User).filter(
                User.organization_id == organization_id,
                User.role.in_(["Owner", "Admin"]),
                OAuthAccount.provider.in_(["gbp", "google"])
            ).first()
            if oauth_account:
                db.delete(oauth_account)
                db.commit()
            
        # Log failure securely
        error_msg = f"Sync Failed: {str(e)}"
        db.query(SyncLog).filter(SyncLog.id == sync_log.id).update({
            SyncLog.status: "Failed",
            SyncLog.error_message: error_msg
        })
        
        # Flag existing locations as failed
        db.query(Location).filter(Location.organization_id == organization_id).update({
            Location.sync_status: "Failed"
        })
        db.commit()
        
        raise e
        
    finally:
        try:
            lock.release()
        except Exception:
            pass
        db.close()

@shared_task(name="app.tasks.sync_all_organizations_task")
def sync_all_organizations_task() -> str:
    """
    Periodic task enqueuing one background sync per organization.
    Picks the active Owner/Admin with the freshest OAuth token for each org
    to avoid queuing redundant tasks when multiple admins have connected accounts.
    """
    db: Session = SessionLocal()
    try:
        # Fetch all active Owner/Admin users who have a connected OAuth account,
        # ordered so the freshest token comes first within each organization.
        users_with_google = (
            db.query(User)
            .join(OAuthAccount, OAuthAccount.user_id == User.id)
            .filter(
                User.role.in_(["Owner", "Admin"]),
                User.is_active == True
            )
            .order_by(OAuthAccount.expires_at.desc())
            .all()
        )

        # Deduplicate: keep only the first (freshest-token) admin per org.
        best_admin_per_org: dict[int, User] = {}
        for admin in users_with_google:
            if admin.organization_id not in best_admin_per_org:
                best_admin_per_org[admin.organization_id] = admin

        triggered_count = 0
        for org_id, admin in best_admin_per_org.items():
            sync_locations_task.delay(org_id, admin.id, "Scheduled")
            triggered_count += 1

        return f"Triggered synchronization for {triggered_count} organizations."
    finally:
        db.close()


@shared_task(bind=True, name="app.tasks.tag_reviews_sentiment_task", max_retries=2)
def tag_reviews_sentiment_task(self, location_id: int, organization_id: int) -> dict:
    """
    Background task that classifies untagged reviews for a location using the LLM sentiment service.
    Acquires a Redis lock to prevent overlapping runs.
    Does NOT write to sync_logs — sentiment tagging is background enrichment, not a sync event.
    """
    import redis
    from app.core.config import settings
    from app.models.review import Review
    from app.services.sentiment_service import tag_reviews_sentiment
    import logging

    logger = logging.getLogger(__name__)

    r = redis.Redis.from_url(settings.REDIS_URL)
    lock_key = f"lock:sentiment_tag:{organization_id}:{location_id}"
    lock = r.lock(lock_key, timeout=600)

    if not lock.acquire(blocking=False):
        return {"status": "skipped", "reason": "already running"}

    db: Session = SessionLocal()
    try:
        # Query reviews where:
        # - location and org match
        # - sentiment_tagged_at IS NULL (not yet processed)
        # - not soft deleted
        # TODO (future): also include reviews where review_updated_at > sentiment_tagged_at
        # to automatically re-classify reviews whose text changed after initial tagging.
        untagged_reviews = db.query(Review).filter(
            Review.location_id == location_id,
            Review.organization_id == organization_id,
            Review.sentiment_tagged_at == None,  # noqa: E711
            Review.is_deleted == False
        ).all()

        if not untagged_reviews:
            return {"status": "skipped", "reason": "no untagged reviews"}

        asyncio.run(tag_reviews_sentiment(untagged_reviews, db))

        return {"status": "completed", "tagged": len(untagged_reviews)}

    except Exception as e:
        logger.error("Sentiment tagging task failed for location %s: %s", location_id, str(e))
        raise
    finally:
        try:
            lock.release()
        except Exception:
            pass
        db.close()
