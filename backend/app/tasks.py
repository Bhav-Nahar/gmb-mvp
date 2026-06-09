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

def run_async(coro):
    """
    Run an async coroutine synchronously.
    Uses asyncio.run() to ensure thread safety across Celery workers.
    """
    return asyncio.run(coro)

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
        
        r = redis.Redis.from_url(settings.REDIS_URL, socket_timeout=5, socket_connect_timeout=5)
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
            
            result = run_async(ReviewSyncService.sync_location_reviews(db, location_id, run_type, sync_log_id=sync_log.id))

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

@shared_task(bind=True, name="app.tasks.sync_reviews_chunk_task")
def sync_reviews_chunk_task(self, location_ids: list, organization_id: int, run_type: str = "Scheduled", user_id: int = None) -> dict:
    """
    Synchronizes reviews for a chunk of locations.
    Contains isolated exception handling, idempotency locks, and rate limiting to protect the API.
    """
    import redis
    import time
    import logging
    from app.core.config import settings
    from sqlalchemy.orm import Session
    from app.db.session import SessionLocal
    from app.models.location import Location
    from app.models.sync_log import SyncLog
    from app.services.review_sync_service import ReviewSyncService

    logger = logging.getLogger(__name__)
    db: Session = SessionLocal()
    r = redis.Redis.from_url(settings.REDIS_URL, socket_timeout=5, socket_connect_timeout=5)

    results = []
    
    try:
        for loc_id in location_ids:
            sync_log = None
            lock_key = f"lock:sync_reviews:{organization_id}:{loc_id}"
            lock = r.lock(lock_key, timeout=300)
            
            if not lock.acquire(blocking=False):
                logger.info(f"Skipped sync for location {loc_id} - already in progress", extra={
                    "organization_id": organization_id,
                    "location_id": loc_id,
                    "task_id": self.request.id
                })
                results.append({"location_id": loc_id, "status": "skipped", "reason": "sync already in progress"})
                continue
                
            try:
                sync_log = SyncLog(
                    organization_id=organization_id,
                    location_id=loc_id,
                    status="Pending",
                    run_type=run_type,
                    error_message=None
                )
                db.add(sync_log)
                db.commit()
                db.refresh(sync_log)

                loc = db.query(Location).filter(Location.id == loc_id).first()
                google_location_id = loc.google_location_id if loc else "unknown"

                logger.info("Starting review sync", extra={
                    "organization_id": organization_id,
                    "location_id": loc_id,
                    "task_id": self.request.id,
                    "google_location_id": google_location_id
                })

                result = run_async(ReviewSyncService.sync_location_reviews(db, loc_id, run_type, sync_log_id=sync_log.id))
                results.append({"location_id": loc_id, "status": "success", "result": result})

            except Exception as e:
                db.rollback()
                google_location_id = locals().get('google_location_id', 'unknown')
                logger.error(f"Sync failed for location {loc_id}: {str(e)}", extra={
                    "organization_id": organization_id,
                    "location_id": loc_id,
                    "task_id": self.request.id,
                    "google_location_id": google_location_id
                })
                
                if 'sync_log' in locals() and sync_log and sync_log.id:
                    db.query(SyncLog).filter(SyncLog.id == sync_log.id).update({
                        SyncLog.status: "Failed",
                        SyncLog.error_message: f"Sync Failed: {str(e)}"
                    })
                    db.commit()
                
                results.append({"location_id": loc_id, "status": "error", "reason": str(e)})
            finally:
                try:
                    lock.release()
                except Exception:
                    pass
                
                # Rate limiting / Sleep in chunk
                time.sleep(getattr(settings, "REVIEW_SYNC_SLEEP_SECONDS", 0.2))

        return {"status": "completed", "results": results}
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
    from app.models.organization_sync_state import OrganizationSyncState
    
    db: Session = SessionLocal()
    
    r = redis.Redis.from_url(settings.REDIS_URL, socket_timeout=5, socket_connect_timeout=5)
    lock_key = f"lock:sync_locations:org_{organization_id}"
    lock = r.lock(lock_key, timeout=3600)  # 1-hour lease to protect sync window
    
    if not lock.acquire(blocking=False):
        db.close()
        return {"status": "skipped", "reason": "sync already in progress"}
    
    # Locate or create sync state within the lock
    sync_state = db.query(OrganizationSyncState).filter(
        OrganizationSyncState.organization_id == organization_id
    ).first()
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    if not sync_state:
        sync_state = OrganizationSyncState(
            organization_id=organization_id,
            sync_in_progress=True,
            sync_started_at=now_utc,
            last_sync_status="Pending"
        )
        db.add(sync_state)
    else:
        sync_state.sync_in_progress = True
        sync_state.sync_started_at = now_utc
        sync_state.last_sync_status = "Pending"
    db.commit()
    db.refresh(sync_state)
    
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
        provider_locations = run_async(provider.get_locations())
        
        # Pre-fetch all locations for this org to prevent N+1 query inside loop
        existing_locations = db.query(Location).filter(Location.organization_id == organization_id).all()
        existing_locs_map = {loc.google_location_id: loc for loc in existing_locations}
        
        synced_count = 0
        sync_jobs = []
        for p_loc in provider_locations:
            # Removed debug print
            
            # Check if location already exists in db via map
            existing_loc = existing_locs_map.get(p_loc.provider_location_id)
            
            if existing_loc:
                # Update
                existing_loc.google_account_id = p_loc.google_account_id
                existing_loc.location_name = p_loc.name
                existing_loc.primary_category = p_loc.category
                existing_loc.address = p_loc.address
                existing_loc.phone = p_loc.phone
                existing_loc.website = p_loc.website
                existing_loc.description = p_loc.description
                existing_loc.business_hours = p_loc.business_hours
                if p_loc.average_rating is not None:
                    existing_loc.average_rating = p_loc.average_rating
                if p_loc.total_reviews is not None:
                    existing_loc.total_reviews = p_loc.total_reviews
                
                # Update state attributes
                if p_loc.is_verified is not None:
                    existing_loc.is_verified = p_loc.is_verified
                    existing_loc.is_suspended = p_loc.is_suspended
                    existing_loc.is_duplicate = p_loc.is_duplicate
                
                existing_loc.sync_status = "Synced"
                existing_loc.last_synced_at = datetime.datetime.now(datetime.timezone.utc)
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
                    description=p_loc.description,
                    business_hours=p_loc.business_hours,
                    average_rating=p_loc.average_rating,
                    total_reviews=p_loc.total_reviews,
                    is_verified=p_loc.is_verified,
                    is_suspended=p_loc.is_suspended,
                    is_duplicate=p_loc.is_duplicate,
                    sync_status="Synced",
                    last_synced_at=datetime.datetime.now(datetime.timezone.utc)
                )
                db.add(new_loc)
                db.flush()
                loc_id = new_loc.id
                
            sync_jobs.append(loc_id)
            synced_count += 1
            
        # Commit once after the loop
        db.commit()
        
        # Trigger review sync in chunks
        import time
        chunk_size = getattr(settings, "REVIEW_SYNC_CHUNK_SIZE", 20)
        for i in range(0, len(sync_jobs), chunk_size):
            chunk = sync_jobs[i:i + chunk_size]
            sync_reviews_chunk_task.delay(chunk, organization_id, run_type, user_id)
            time.sleep(0.1)
            
        # Trigger attribute sync
        for loc_id in sync_jobs:
            sync_location_attributes_task.delay(loc_id)
            
        # Log successful sync operation
        log_message = f"Synchronized {synced_count} locations successfully."
        sync_log.status = "Success"
        sync_log.error_message = log_message
        
        # Update organization sync state
        sync_state.sync_in_progress = False
        sync_state.sync_started_at = None  # Clear: no sync in flight
        sync_state.last_sync_status = "Success"
        sync_state.last_location_sync_at = datetime.datetime.now(datetime.timezone.utc)
        sync_state.last_sync_error = None
        
        db.commit()
        
        return {"status": "success", "result": log_message}

    except Exception as e:
        db.rollback()
        
        # If refreshing has failed catastrophically
        from app.providers.gbp.auth import PermanentAuthError
        if isinstance(e, PermanentAuthError):
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
        
        # Update organization sync state on failure
        sync_state.sync_in_progress = False
        sync_state.sync_started_at = None  # Clear: no sync in flight
        sync_state.last_sync_status = "Failed"
        sync_state.last_sync_error = error_msg
        
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
        # Deduplicate at the query level or fetch only what we need to avoid massive memory usage
        users_with_google = (
            db.query(User.id, User.organization_id)
            .join(OAuthAccount, OAuthAccount.user_id == User.id)
            .filter(
                User.role.in_(["Owner", "Admin"]),
                User.is_active == True
            )
            .order_by(OAuthAccount.expires_at.desc())
            .all()
        )

        # Deduplicate: keep only the first (freshest-token) admin per org.
        best_admin_per_org = {}
        for admin_id, org_id in users_with_google:
            if org_id not in best_admin_per_org:
                best_admin_per_org[org_id] = admin_id

        triggered_count = 0
        for org_id, admin_id in best_admin_per_org.items():
            sync_locations_task.delay(org_id, admin_id, "Scheduled")
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

    r = redis.Redis.from_url(settings.REDIS_URL, socket_timeout=5, socket_connect_timeout=5)
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

        run_async(tag_reviews_sentiment(untagged_reviews, db))

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

@shared_task(bind=True, name="app.tasks.process_review_sentiment_task", max_retries=2)
def process_review_sentiment_task(self, review_id: int) -> dict:
    import asyncio
    import logging
    from app.db.session import SessionLocal
    from app.models.review import Review
    from app.services.sentiment_service import tag_reviews_sentiment

    logger = logging.getLogger(__name__)

    db = SessionLocal()
    try:
        review = db.query(Review).filter(Review.id == review_id, Review.is_deleted == False).first()
        if not review or review.sentiment_tagged_at is not None:
            return {"status": "skipped", "reason": "Review not found or already tagged"}
            
        run_async(tag_reviews_sentiment([review], db))
        return {"status": "completed", "review_id": review_id}
    except Exception as e:
        logger.error(f"process_review_sentiment_task failed for review {review_id}: {e}")
        raise self.retry(exc=e, countdown=60)
    finally:
        db.close()

@shared_task(bind=True, name="app.tasks.process_publish_job_task", max_retries=3)
def process_publish_job_task(self, job_id: int, organization_id: int) -> dict:
    """
    Background worker that physically posts content to Google Business Profile for a single location.
    Secured with Redis lock and idempotency key checks.
    """
    import redis
    import logging
    import httpx
    from app.core.config import settings
    from app.db.session import SessionLocal
    from sqlalchemy.orm import Session
    from app.models.publish_job import PublishJob
    from app.models.post import Post
    from app.models.location import Location
    from app.models.post_variant import PostVariant
    from app.models.post_audit_log import PostAuditLog
    from app.constants.posts import PublishJobStatus, PostStatus
    from app.providers.gbp.post_mapper import GBPPostMapper
    from app.providers.factory import ProviderFactory
    from app.providers.gbp.auth import PermanentAuthError
    
    logger = logging.getLogger(__name__)
    
    r = redis.Redis.from_url(settings.REDIS_URL, socket_timeout=5, socket_connect_timeout=5)
    lock_key = f"lock:publish_job:{organization_id}:{job_id}"
    lock = r.lock(lock_key, timeout=120)
    
    if not lock.acquire(blocking=False):
        return {"status": "skipped", "reason": "Job is currently being processed by another worker"}
        
    db: Session = SessionLocal()
    try:
        logger.info(f"Processing PublishJob {job_id} for Organization {organization_id}")
        job = db.query(PublishJob).filter(PublishJob.id == job_id, PublishJob.organization_id == organization_id).first()
        if not job or job.status not in [PublishJobStatus.PENDING.value, PublishJobStatus.RETRYING.value]:
            return {"status": "skipped", "reason": "Job not found or not in a processable state"}

        # State transition to RUNNING
        job.status = PublishJobStatus.RUNNING.value
        db.commit()

        # Fetch parent post and location details
        post = db.query(Post).filter(Post.id == job.post_id).first()
        location = db.query(Location).filter(Location.id == job.location_id).first()
        if not post or not location:
            raise Exception("Post or Location linked to PublishJob not found.")

        # Find dynamic variant if exists
        variant = db.query(PostVariant).filter(
            PostVariant.post_id == post.id,
            PostVariant.location_id == location.id
        ).first()

        # Map dynamic payload using mapper
        payload = GBPPostMapper.to_gbp_payload(post, variant)

        # Retrieve Google Business Profile Provider dynamically
        provider = ProviderFactory.get_provider("gbp", organization_id, db)

        # Sync/Async invocation: internally provider.create_post is fully async but called here synchronously
        res = run_async(provider.create_post(location.google_location_id, payload))

        # Simulating/Parsing successful Google API response
        job.status = PublishJobStatus.SUCCESS.value
        job.google_post_id = res.id
        job.provider_response = getattr(res, "provider_metadata", {}) or {}
        job.published_at = datetime.datetime.now(timezone.utc)
        
        # Atomically transition parent Post to PUBLISHED
        if not job.campaign_id:
            post.status = PostStatus.PUBLISHED.value
        
        # Atomic campaign counter update
        if job.campaign_id:
            from app.models.campaign import Campaign
            from app.models.campaign_audit_log import CampaignAuditLog
            from sqlalchemy import func
            db.query(Campaign).filter(Campaign.id == job.campaign_id).update({
                Campaign.total_published: Campaign.total_published + 1,
                Campaign.total_pending: func.greatest(0, Campaign.total_pending - 1)
            }, synchronize_session=False)
            
            campaign = db.query(Campaign).filter(Campaign.id == job.campaign_id).first()
            if campaign and campaign.total_pending == 0:
                old_status = campaign.status
                if campaign.total_failed == 0:
                    new_status = "Completed"
                elif campaign.total_published == 0:
                    new_status = "Failed"
                else:
                    new_status = "PartiallyCompleted"
                    
                campaign.status = new_status
                db.add(CampaignAuditLog(
                    organization_id=organization_id,
                    campaign_id=campaign.id,
                    actor_user_id=None,
                    action="completed",
                    previous_status=old_status,
                    new_status=new_status,
                    log_metadata={"final_stats": {"published": campaign.total_published, "failed": campaign.total_failed}}
                ))
        
        # Save a PostAuditLog
        audit_log = PostAuditLog(
            organization_id=organization_id,
            post_id=post.id,
            action="PUBLISHED",
            previous_status="PUBLISHING",
            new_status=PostStatus.PUBLISHED.value,
            log_metadata={
                "google_post_id": res.id,
                "location_id": location.id,
                "publish_job_id": job.id
            }
        )
        db.add(audit_log)
        
        from app.services.activity_log_service import ActivityLogService
        ActivityLogService.log(
            db,
            organization_id=organization_id,
            location_id=location.id,
            actor_user_id=None,
            entity_type="post",
            entity_id=post.id,
            action="post_published",
            payload={"google_post_id": res.id}
        )
        
        db.commit()
        
        return {"status": "completed", "google_post_id": job.google_post_id}
    except Exception as e:
        logger.error(f"PublishJob {job_id} failed: {str(e)}")
        db.rollback()
        
        # Decide if error is retryable or not
        is_retryable = True
        
        if isinstance(e, PermanentAuthError):
            is_retryable = False
        elif isinstance(e, httpx.HTTPStatusError):
            # Client errors (except 429) are usually non-retryable
            if e.response.status_code in [400, 401, 403, 404, 409]:
                is_retryable = False
        elif not isinstance(e, (httpx.RequestError, TimeoutError, ConnectionError)):
            # System logic/code exceptions are non-retryable
            is_retryable = False
            
        # Re-fetch job/post inside a fresh session to record the failure safely
        job_db = SessionLocal()
        try:
            job_record = job_db.query(PublishJob).filter(PublishJob.id == job_id).first()
            post_record = job_db.query(Post).filter(Post.id == job.post_id).first() if job else None
            
            if job_record:
                # Capture status details from the exception safely
                err_data = {}
                if isinstance(e, httpx.HTTPStatusError):
                    try:
                        err_data = e.response.json()
                    except Exception:
                        err_data = {"raw_response": e.response.text}
                
                if is_retryable and self.request.retries < self.max_retries:
                    job_record.status = PublishJobStatus.RETRYING.value
                    job_record.last_error = str(e)
                    job_record.retry_count = self.request.retries + 1
                    job_record.provider_response = err_data
                    job_db.commit()
                    
                    # Celery retry countdown
                    countdown = 60 * (2 ** self.request.retries)
                    job_db.close()
                    raise self.retry(exc=e, countdown=countdown)
                else:
                    # Mark permanent or final run failure
                    job_record.status = PublishJobStatus.FAILED.value
                    job_record.last_error = str(e)
                    job_record.provider_response = err_data
                    
                    if post_record and not job_record.campaign_id:
                        post_record.status = PostStatus.FAILED.value
                        
                        # Save a PostAuditLog
                        audit_log = PostAuditLog(
                            organization_id=organization_id,
                            post_id=post_record.id,
                            action="PUBLISH_FAILED",
                            previous_status="PUBLISHING",
                            new_status=PostStatus.FAILED.value,
                            log_metadata={
                                "error": str(e),
                                "publish_job_id": job_record.id
                            }
                        )
                        job_db.add(audit_log)
                        
                    if job_record.campaign_id:
                        from app.models.campaign import Campaign
                        from app.models.campaign_audit_log import CampaignAuditLog
                        from sqlalchemy import func
                        job_db.query(Campaign).filter(Campaign.id == job_record.campaign_id).update({
                            Campaign.total_failed: Campaign.total_failed + 1,
                            Campaign.total_pending: func.greatest(0, Campaign.total_pending - 1)
                        }, synchronize_session=False)
                        
                        campaign = job_db.query(Campaign).filter(Campaign.id == job_record.campaign_id).first()
                        if campaign and campaign.total_pending == 0:
                            old_status = campaign.status
                            if campaign.total_failed == 0:
                                new_status = "Completed"
                            elif campaign.total_published == 0:
                                new_status = "Failed"
                            else:
                                new_status = "PartiallyCompleted"
                                
                            campaign.status = new_status
                            job_db.add(CampaignAuditLog(
                                organization_id=organization_id,
                                campaign_id=campaign.id,
                                actor_user_id=None,
                                action="completed",
                                previous_status=old_status,
                                new_status=new_status,
                                log_metadata={"final_stats": {"published": campaign.total_published, "failed": campaign.total_failed}}
                            ))
                    
                    job_db.commit()
        finally:
            job_db.close()
            
        raise e
    finally:
        try:
            lock.release()
        except Exception:
            pass
        db.close()

@shared_task(bind=True, name="app.tasks.orchestrate_campaign_task", max_retries=30)
def orchestrate_campaign_task(self, campaign_id: int, organization_id: int, location_ids: list, user_id: int) -> dict:
    import logging
    from app.db.session import SessionLocal
    from sqlalchemy.orm import Session
    from app.models.campaign import Campaign
    from app.models.post import Post
    from app.models.location import Location
    from app.models.publish_job import PublishJob
    from app.models.post_variant import PostVariant
    from app.constants.posts import CampaignStatus, PublishJobStatus
    from app.models.campaign_audit_log import CampaignAuditLog
    import re
    
    logger = logging.getLogger(__name__)
    db: Session = SessionLocal()
    staged_jobs = []
    
    try:
        campaign = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.organization_id == organization_id).first()
        if not campaign:
            return {"status": "error", "reason": "Campaign not found"}
            
        old_status = campaign.status
        campaign.status = CampaignStatus.PROCESSING.value
        
        db.add(CampaignAuditLog(
            organization_id=organization_id,
            campaign_id=campaign.id,
            actor_user_id=user_id,
            action="started",
            previous_status=old_status,
            new_status=CampaignStatus.PROCESSING.value,
            log_metadata={"action": "orchestration_started"}
        ))
        
        # Explicit primary_post_id linkage with fallback
        post = None
        if campaign.primary_post_id:
            post = db.query(Post).filter(Post.id == campaign.primary_post_id).first()
        if not post:
            post = db.query(Post).filter(Post.campaign_id == campaign.id).order_by(Post.id.asc()).first()
            
        if not post:
            campaign.status = CampaignStatus.FAILED.value
            db.add(CampaignAuditLog(
                organization_id=organization_id,
                campaign_id=campaign.id,
                actor_user_id=user_id,
                action="failed",
                previous_status=CampaignStatus.PROCESSING.value,
                new_status=CampaignStatus.FAILED.value,
                log_metadata={"error": "No posts attached to campaign"}
            ))
            db.commit()
            return {"status": "error", "reason": "No posts attached to campaign"}

        # Wait for Media Optimization & Validation (Bug 2)
        attached_media = [m for m in post.media if not m.is_deleted]
        if attached_media:
            # 1. Fail fast if any media is permanently invalid or upload failed
            invalid_media = [m for m in attached_media if m.validation_status == "Invalid" or m.upload_status == "Failed"]
            if invalid_media:
                campaign.status = CampaignStatus.FAILED.value
                db.add(CampaignAuditLog(
                    organization_id=organization_id,
                    campaign_id=campaign.id,
                    actor_user_id=user_id,
                    action="failed",
                    previous_status=CampaignStatus.PROCESSING.value,
                    new_status=CampaignStatus.FAILED.value,
                    log_metadata={"error": "Campaign post contains invalid or failed media."}
                ))
                db.commit()
                return {"status": "error", "reason": "Campaign post contains invalid or failed media."}

            # 2. Check for pending optimization or validation
            unready_media = [m for m in attached_media if not m.optimized_url or m.validation_status == "Pending" or m.upload_status == "Pending"]
            if unready_media:
                current_retry = self.request.retries
                # Keep campaign in PROCESSING status
                if campaign.status != CampaignStatus.PROCESSING.value:
                    campaign.status = CampaignStatus.PROCESSING.value
                    db.commit()
                
                if current_retry < 30: # 5 minutes total (30 retries * 10 seconds)
                    logger.info(f"Campaign {campaign_id}: Media is still optimizing. Retrying orchestrator task in 10 seconds. (Retry {current_retry + 1}/30)")
                    db.commit()
                    db.close()
                    raise self.retry(countdown=10, max_retries=30)
                else:
                    campaign.status = CampaignStatus.FAILED.value
                    db.add(CampaignAuditLog(
                        organization_id=organization_id,
                        campaign_id=campaign.id,
                        actor_user_id=user_id,
                        action="failed",
                        previous_status=CampaignStatus.PROCESSING.value,
                        new_status=CampaignStatus.FAILED.value,
                        log_metadata={"error": "Media optimization timed out (exceeded 5 minutes)."}
                    ))
                    db.commit()
                    return {"status": "error", "reason": "Media optimization timed out."}
        # Delete existing variants and jobs to prevent unique constraint failures on relaunch
        db.query(PostVariant).filter(
            PostVariant.post_id == post.id,
            PostVariant.location_id.in_(location_ids)
        ).delete(synchronize_session=False)
        db.query(PublishJob).filter(
            PublishJob.post_id == post.id,
            PublishJob.location_id.in_(location_ids)
        ).delete(synchronize_session=False)
        db.flush()

        locations = db.query(Location).filter(Location.id.in_(location_ids)).all()
        loc_map = {l.id: l for l in locations}
        
        for loc_id in location_ids:
            loc = loc_map.get(loc_id)
            if not loc:
                continue
                
            # City Parser logic (supporting JSON address)
            city = loc.location_name
            if loc.address:
                try:
                    import json
                    if loc.address.startswith("{"):
                        addr_dict = json.loads(loc.address)
                        city = addr_dict.get("locality") or loc.location_name
                    else:
                        raise ValueError()
                except Exception:
                    parts = [p.strip() for p in loc.address.split(',')]
                    found_city = False
                    for i, part in enumerate(parts):
                        if re.search(r'\b\d{5}\b', part) or re.search(r'\b[A-Z]{2}\s\d{5}\b', part):
                            if i > 0:
                                city = parts[i-1]
                                found_city = True
                                break
                    if not found_city and len(parts) >= 3:
                        city = parts[-3]
            
            summary_template = post.summary or ""
            rendered_summary = summary_template.replace("{{location}}", loc.location_name).replace("{{city}}", city).replace("{{phone}}", loc.phone or "")
            rendered_summary = re.sub(r'\{[^{}]+\}', '', rendered_summary)
            
            cta_template = post.cta_url or ""
            rendered_cta_url = cta_template.replace("{{location_id}}", str(loc.id)) if cta_template else None
            if rendered_cta_url:
                rendered_cta_url = re.sub(r'\{[^{}]+\}', '', rendered_cta_url)
            
            if rendered_cta_url:
                from app.utils.utm_generator import generate_utm_link
                raw_type = post.post_type
                if hasattr(raw_type, "value"):
                    raw_type = raw_type.value
                touchpoint = str(raw_type).lower()
                
                rendered_cta_url = generate_utm_link(
                    base_url=rendered_cta_url,
                    location_id=str(loc.id),
                    touchpoint=touchpoint
                )
            
            variant = PostVariant(
                organization_id=organization_id,
                post_id=post.id,
                location_id=loc.id,
                rendered_summary=rendered_summary,
                rendered_cta_url=rendered_cta_url,
                rendering_variables={"city": city}
            )
            db.add(variant)
            
            job = PublishJob(
                organization_id=organization_id,
                campaign_id=campaign.id,
                post_id=post.id,
                location_id=loc.id,
                provider="gbp",
                status=PublishJobStatus.PENDING.value
            )
            db.add(job)
            staged_jobs.append(job)
            
        # No Inline Dispatch Rule: commit all DB changes first!
        db.commit()
        # Collect job IDs for dispatch
        job_ids = [job.id for job in staged_jobs]
    except Exception as e:
        db.rollback()
        logger.error(f"Orchestration failed for campaign {campaign_id}: {str(e)}")
        
        job_db = SessionLocal()
        try:
            from app.models.campaign import Campaign
            from app.models.campaign_audit_log import CampaignAuditLog
            campaign_err = job_db.query(Campaign).filter(Campaign.id == campaign_id).first()
            if campaign_err:
                old_status = campaign_err.status
                campaign_err.status = CampaignStatus.FAILED.value
                job_db.add(CampaignAuditLog(
                    organization_id=organization_id,
                    campaign_id=campaign_err.id,
                    actor_user_id=user_id,
                    action="failed",
                    previous_status=old_status,
                    new_status=CampaignStatus.FAILED.value,
                    log_metadata={"error": str(e)}
                ))
                job_db.commit()
        finally:
            job_db.close()
            
        raise
    finally:
        db.close()
        
    # Boundary crossed: DB is committed. Now chunk jobs and dispatch campaign shards.
    shards_count = 0
    if job_ids:
        import time
        import redis
        from app.core.config import settings
        
        chunk_size = 50
        shards = [job_ids[i:i + chunk_size] for i in range(0, len(job_ids), chunk_size)]
        shards_count = len(shards)
        
        r = redis.Redis.from_url(settings.REDIS_URL, socket_timeout=5, socket_connect_timeout=5)
        r.set(f"campaign:{campaign_id}:pending_shards", len(shards))
        r.set(f"campaign:{campaign_id}:success", 0)
        r.set(f"campaign:{campaign_id}:failed", 0)
        r.set(f"campaign:{campaign_id}:total_locations", len(job_ids))
        r.set(f"campaign:{campaign_id}:status", "Processing")
        
        for shard in shards:
            process_campaign_shard_task.delay(shard, organization_id, campaign_id)
            time.sleep(0.1)

    return {"status": "success", "jobs_created": len(job_ids), "shards_created": shards_count}


@shared_task(bind=True, name="app.tasks.process_campaign_shard_task", max_retries=1)
def process_campaign_shard_task(self, job_ids: list, organization_id: int, campaign_id: int) -> dict:
    """
    Processes a shard of publish jobs sequentially with adaptive rate limiting,
    jitter, circuit breaking, and atomic Redis-backed PostgreSQL updates.
    """
    import time
    import random
    import redis
    import logging
    import httpx
    import asyncio
    import datetime
    from app.core.config import settings
    from app.db.session import SessionLocal
    from sqlalchemy.orm import Session
    from app.models.publish_job import PublishJob
    from app.models.post import Post
    from app.models.location import Location
    from app.models.post_variant import PostVariant
    from app.models.post_audit_log import PostAuditLog
    from app.models.campaign import Campaign
    from app.models.campaign_audit_log import CampaignAuditLog
    from app.constants.posts import PublishJobStatus, CampaignStatus, PostStatus
    from app.providers.gbp.post_mapper import GBPPostMapper
    from app.providers.factory import ProviderFactory
    from app.providers.gbp.auth import PermanentAuthError
    
    logger = logging.getLogger(__name__)
    r = redis.Redis.from_url(settings.REDIS_URL, socket_timeout=5, socket_connect_timeout=5)
    
    shard_success = 0
    shard_failed = 0
    shard_paused_cancelled = 0
    
    # Pre-flight campaign status check
    campaign_status = (r.get(f"campaign:{campaign_id}:status") or b"").decode("utf-8")
    if campaign_status in ["Paused", "Cancelled"]:
        # Circuit breaker tripped before we even start
        db = SessionLocal()
        try:
            # Drain/mark all remaining jobs as PAUSED or CANCELLED
            status_val = PublishJobStatus.PAUSED.value if campaign_status == "Paused" else PublishJobStatus.CANCELLED.value
            db.query(PublishJob).filter(PublishJob.id.in_(job_ids)).update(
                {PublishJob.status: status_val}, synchronize_session=False
            )
            db.commit()
            shard_paused_cancelled = len(job_ids)
        except Exception as ex:
            db.rollback()
            logger.error(f"Failed to drain campaign jobs on pre-flight circuit breaker: {str(ex)}")
        finally:
            db.close()
            
        # Decrement pending shards and handle terminal state check
        _decr_and_flush_terminal_state(r, campaign_id, organization_id, shard_success, shard_failed, shard_paused_cancelled)
        return {"status": "aborted", "reason": f"Campaign is {campaign_status}"}

    try:
        # Loop over shard jobs sequentially
        cached_status = campaign_status
        for idx, job_id in enumerate(job_ids):
            # 1. Double check Campaign Status periodically (every 5 jobs) 
            # instead of every single job to save Redis requests
            if idx > 0 and idx % 5 == 0:
                cached_status = (r.get(f"campaign:{campaign_id}:status") or b"").decode("utf-8")

            if cached_status in ["Paused", "Cancelled"]:
                # Circuit breaker tripped mid-shard
                logger.info(f"Campaign {campaign_id} transitioned to {cached_status}. Tripping circuit breaker for remaining jobs in shard.")
                remaining_ids = job_ids[idx:]
                db = SessionLocal()
                try:
                    status_val = PublishJobStatus.PAUSED.value if cached_status == "Paused" else PublishJobStatus.CANCELLED.value
                    db.query(PublishJob).filter(PublishJob.id.in_(remaining_ids)).update(
                        {PublishJob.status: status_val}, synchronize_session=False
                    )
                    db.commit()
                    shard_paused_cancelled += len(remaining_ids)
                except Exception as ex:
                    db.rollback()
                    logger.error(f"Failed to drain remaining campaign jobs on mid-shard circuit breaker: {str(ex)}")
                finally:
                    db.close()
                break

            # 2. Queue Jitter & Adaptive Pacing (between sequential requests in a shard)
            if idx > 0:
                jitter = random.uniform(0.8, 1.5)
                time.sleep(jitter)

            # 3. Process individual job
            db = SessionLocal()
            try:
                job = db.query(PublishJob).filter(PublishJob.id == job_id, PublishJob.organization_id == organization_id).first()
                if not job or job.status not in [PublishJobStatus.PENDING.value, PublishJobStatus.RETRYING.value]:
                    shard_paused_cancelled += 1
                    continue

                job.status = PublishJobStatus.RUNNING.value
                db.commit()

                post = db.query(Post).filter(Post.id == job.post_id).first()
                location = db.query(Location).filter(Location.id == job.location_id).first()
                if not post or not location:
                    raise Exception("Post or Location linked to PublishJob not found.")

                variant = db.query(PostVariant).filter(
                    PostVariant.post_id == post.id,
                    PostVariant.location_id == location.id
                ).first()

                payload = GBPPostMapper.to_gbp_payload(post, variant)
                provider = ProviderFactory.get_provider("gbp", organization_id, db)

                # Invoke provider.create_post
                res = run_async(provider.create_post(location.google_location_id, payload))

                # Job Success
                job.status = PublishJobStatus.SUCCESS.value
                job.google_post_id = res.id
                job.provider_response = getattr(res, "provider_metadata", {}) or {}
                job.published_at = datetime.datetime.now(datetime.timezone.utc)

                # Save PostAuditLog
                audit_log = PostAuditLog(
                    organization_id=organization_id,
                    post_id=post.id,
                    action="PUBLISHED",
                    previous_status="PUBLISHING",
                    new_status=PostStatus.PUBLISHED.value,
                    log_metadata={
                        "google_post_id": res.id,
                        "location_id": location.id,
                        "publish_job_id": job.id
                    }
                )
                db.add(audit_log)
                db.commit()

                # Increment success counters
                r.incr(f"campaign:{campaign_id}:success")
                shard_success += 1

            except Exception as e:
                db.rollback()
                logger.error(f"Job {job_id} in shard failed: {str(e)}")
                
                # Transient vs Permanent Error Classification
                is_retryable = True
                if isinstance(e, PermanentAuthError):
                    is_retryable = False
                elif isinstance(e, httpx.HTTPStatusError):
                    # 429, 502, 503, timeouts are Transient. Others are Permanent.
                    if e.response.status_code in [400, 401, 403, 404, 409]:
                        is_retryable = False
                elif not isinstance(e, (httpx.RequestError, TimeoutError, ConnectionError)):
                    is_retryable = False

                # Capture details safely
                err_data = {}
                if isinstance(e, httpx.HTTPStatusError):
                    try:
                        err_data = e.response.json()
                    except Exception:
                        err_data = {"raw_response": e.response.text}

                job_db = SessionLocal()
                try:
                    job_record = job_db.query(PublishJob).filter(PublishJob.id == job_id).first()
                    post_record = job_db.query(Post).filter(Post.id == post.id).first() if post else None
                    
                    if job_record:
                        current_retries = job_record.retry_count
                        if is_retryable and current_retries < 3:
                            # Schedule individual job retry with exponential backoff pacing
                            job_record.status = PublishJobStatus.RETRYING.value
                            job_record.last_error = str(e)
                            job_record.retry_count = current_retries + 1
                            job_record.provider_response = err_data
                            job_db.commit()
                            
                            countdown = 60 * (2 ** current_retries)
                            # Re-enqueue this single job in its own single-element shard
                            # Idempotent retry locking to prevent double registering retry or double-incrementing pending_shards (Bug 3 & 4 refinement)
                            retry_key = f"campaign:{campaign_id}:retry_registered:{job_id}:{current_retries + 1}"
                            if r.set(retry_key, "1", ex=86400, nx=True):
                                r.incr(f"campaign:{campaign_id}:pending_shards")
                                process_campaign_shard_task.apply_async(
                                    args=([job_id], organization_id, campaign_id),
                                    countdown=countdown
                                )
                        else:
                            # Permanent failure
                            job_record.status = PublishJobStatus.FAILED.value
                            job_record.last_error = str(e)
                            job_record.provider_response = err_data
                            
                            if post_record:
                                audit_log = PostAuditLog(
                                    organization_id=organization_id,
                                    post_id=post_record.id,
                                    action="PUBLISH_FAILED",
                                    previous_status="PUBLISHING",
                                    new_status=PostStatus.FAILED.value,
                                    log_metadata={
                                        "error": str(e),
                                        "publish_job_id": job_record.id
                                    }
                                )
                                job_db.add(audit_log)
                            
                            job_db.commit()
                            r.incr(f"campaign:{campaign_id}:failed")
                            shard_failed += 1
                except Exception as retry_err:
                    logger.error(f"Failed to record job failure state: {str(retry_err)}")
                finally:
                    job_db.close()
            finally:
                db.close()
    finally:
        # 4. Flush aggregated shard counters to PostgreSQL (using greatest to prevent negative total_pending)
        if shard_success > 0 or shard_failed > 0 or shard_paused_cancelled > 0:
            db = SessionLocal()
            try:
                from sqlalchemy import func
                db.query(Campaign).filter(Campaign.id == campaign_id).update({
                    Campaign.total_published: Campaign.total_published + shard_success,
                    Campaign.total_failed: Campaign.total_failed + shard_failed,
                    Campaign.total_pending: func.greatest(0, Campaign.total_pending - (shard_success + shard_failed + shard_paused_cancelled))
                }, synchronize_session=False)
                db.commit()
            except Exception as flush_err:
                db.rollback()
                logger.error(f"Failed to flush shard counters to campaign {campaign_id}: {str(flush_err)}")
            finally:
                db.close()

        # 5. Decrement pending shards and transition terminal state if last one
        _decr_and_flush_terminal_state(r, campaign_id, organization_id, shard_success, shard_failed, shard_paused_cancelled)
        
    return {"status": "shard_completed", "success": shard_success, "failed": shard_failed, "paused_cancelled": shard_paused_cancelled}


def _decr_and_flush_terminal_state(r, campaign_id: int, organization_id: int, shard_success: int, shard_failed: int, shard_paused_cancelled: int):
    """
    Atomically decrements the pending shards counter in Redis and,
    if it is the final shard (0), performs the terminal status transition in Postgres.
    """
    import logging
    from app.db.session import SessionLocal
    from app.models.campaign import Campaign
    from app.models.campaign_audit_log import CampaignAuditLog
    from app.constants.posts import CampaignStatus, PostStatus
    
    logger = logging.getLogger(__name__)
    remaining_shards = r.decr(f"campaign:{campaign_id}:pending_shards")
    
    if remaining_shards == 0:
        db = SessionLocal()
        try:
            # HIGH-7 Fix: Use with_for_update() to lock the row and ensure we read the 
            # most up-to-date committed values, preventing race conditions with other 
            # concurrent API requests or workers.
            campaign = db.query(Campaign).filter(
                Campaign.id == campaign_id, 
                Campaign.organization_id == organization_id
            ).with_for_update().first()
            if campaign:
                camp_redis_status = (r.get(f"campaign:{campaign_id}:status") or b"").decode("utf-8")
                
                old_status = campaign.status
                if camp_redis_status == "Paused":
                    new_status = CampaignStatus.PAUSED.value
                elif camp_redis_status == "Cancelled":
                    new_status = CampaignStatus.CANCELLED.value
                else:
                    if campaign.total_failed == 0 and campaign.total_published > 0:
                        new_status = CampaignStatus.COMPLETED.value
                    elif campaign.total_published == 0:
                        new_status = CampaignStatus.FAILED.value
                    else:
                        new_status = CampaignStatus.PARTIALLY_COMPLETED.value
                
                campaign.status = new_status
                
                if campaign.primary_post:
                    if campaign.total_failed == 0 and campaign.total_published > 0:
                        campaign.primary_post.status = PostStatus.PUBLISHED.value
                    elif campaign.total_published == 0:
                        campaign.primary_post.status = PostStatus.FAILED.value
                    else:
                        campaign.primary_post.status = PostStatus.PARTIALLY_PUBLISHED.value
                db.add(CampaignAuditLog(
                    organization_id=organization_id,
                    campaign_id=campaign.id,
                    actor_user_id=None,
                    action="completed",
                    previous_status=old_status,
                    new_status=new_status,
                    log_metadata={
                        "final_stats": {
                            "published": campaign.total_published,
                            "failed": campaign.total_failed,
                            "pending": campaign.total_pending
                        }
                    }
                ))
                db.commit()
                logger.info(f"Campaign {campaign_id} terminal transition to {new_status} completed successfully.")
                
                # Cleanup Redis keys
                r.delete(f"campaign:{campaign_id}:pending_shards")
                r.delete(f"campaign:{campaign_id}:success")
                r.delete(f"campaign:{campaign_id}:failed")
                r.delete(f"campaign:{campaign_id}:total_locations")
                r.delete(f"campaign:{campaign_id}:status")
        except Exception as terminal_err:
            db.rollback()
            logger.error(f"Failed to execute campaign terminal transition for {campaign_id}: {str(terminal_err)}")
        finally:
            db.close()


# ----------------------------------------------------
# Media Pipeline & Background Optimization Tasks
# ----------------------------------------------------

async def _optimize_media_async(media_id: int, organization_id: int) -> dict:
    import io
    import os
    import logging
    from PIL import Image
    from app.models.post_media import PostMedia
    from app.storage.factory import StorageProviderFactory

    logger = logging.getLogger(__name__)
    db = SessionLocal()
    try:
        media = db.query(PostMedia).filter(
            PostMedia.id == media_id,
            PostMedia.organization_id == organization_id
        ).first()
        if not media or media.is_deleted:
            return {"status": "skipped", "reason": "Media not found or deleted"}

        # 1. Instantiate Storage Provider and download original file
        storage_provider = StorageProviderFactory.get_provider(media.storage_provider)
        file_bytes = await storage_provider.read_file(media.storage_key)

        # 2. Open and process with Pillow
        image = Image.open(io.BytesIO(file_bytes))
        width, height = image.size
        
        # Cap longest edge at 2048px
        max_edge = 2048
        if max(width, height) > max_edge:
            if width > height:
                new_width = max_edge
                new_height = int(height * (max_edge / width))
            else:
                new_height = max_edge
                new_width = int(width * (max_edge / height))
            
            # Use LANCZOS for high quality downscaling
            image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
        # Write to byte buffer
        if media.mime_type == "image/png":
            img_format = "PNG"
        elif media.mime_type == "image/webp":
            img_format = "WEBP"
        else:
            img_format = "JPEG"
            
        out_buf = io.BytesIO()
        image.save(out_buf, format=img_format, quality=85, optimize=True)
        optimized_bytes = out_buf.getvalue()

        # 3. Upload optimized file
        base, ext = os.path.splitext(media.storage_key)
        opt_key = f"{base}_optimized{ext}"
        
        opt_url = await storage_provider.upload_file(
            file_data=optimized_bytes,
            key=opt_key,
            mime_type=media.mime_type
        )

        # 4. Save to Database
        media.optimized_url = opt_url
        media.upload_status = "Optimized"
        
        # Update log_metadata
        meta = dict(media.log_metadata or {})
        meta["optimized_size_bytes"] = len(optimized_bytes)
        meta["optimized_width"] = image.width
        meta["optimized_height"] = image.height
        media.log_metadata = meta
        
        db.commit()

        logger.info(
            "Media optimized successfully",
            extra={
                "organization_id": organization_id,
                "media_id": media.id,
                "storage_provider": media.storage_provider,
                "upload_status": "Optimized"
            }
        )
        return {"status": "success", "optimized_url": opt_url}
    except Exception as e:
        logger.error(
            f"Media optimization failed: {str(e)}",
            extra={
                "organization_id": organization_id,
                "media_id": media_id
            }
        )
        db.rollback()
        raise e
    finally:
        db.close()


async def _generate_thumbnail_async(media_id: int, organization_id: int) -> dict:
    import io
    import os
    import logging
    from PIL import Image
    from app.models.post_media import PostMedia
    from app.storage.factory import StorageProviderFactory

    logger = logging.getLogger(__name__)
    db = SessionLocal()
    try:
        media = db.query(PostMedia).filter(
            PostMedia.id == media_id,
            PostMedia.organization_id == organization_id
        ).first()
        if not media or media.is_deleted:
            return {"status": "skipped", "reason": "Media not found or deleted"}

        # 1. Instantiate Storage Provider and download original file
        storage_provider = StorageProviderFactory.get_provider(media.storage_provider)
        file_bytes = await storage_provider.read_file(media.storage_key)

        # 2. Open and process with Pillow
        image = Image.open(io.BytesIO(file_bytes))
        
        # Generate thumbnail maintaining aspect ratio
        image.thumbnail((300, 300), Image.Resampling.LANCZOS)
        
        # Write to byte buffer
        if media.mime_type == "image/png":
            img_format = "PNG"
        elif media.mime_type == "image/webp":
            img_format = "WEBP"
        else:
            img_format = "JPEG"
            
        out_buf = io.BytesIO()
        image.save(out_buf, format=img_format, quality=85, optimize=True)
        thumb_bytes = out_buf.getvalue()

        # 3. Upload thumbnail
        base, ext = os.path.splitext(media.storage_key)
        thumb_key = f"{base}_thumb{ext}"
        
        thumb_url = await storage_provider.upload_file(
            file_data=thumb_bytes,
            key=thumb_key,
            mime_type=media.mime_type
        )

        # 4. Save to Database
        media.thumbnail_url = thumb_url
        meta = dict(media.log_metadata or {})
        meta["thumbnail_size_bytes"] = len(thumb_bytes)
        meta["thumbnail_width"] = image.width
        meta["thumbnail_height"] = image.height
        media.log_metadata = meta
        
        db.commit()

        logger.info(
            "Media thumbnail generated successfully",
            extra={
                "organization_id": organization_id,
                "media_id": media.id,
                "storage_provider": media.storage_provider,
                "upload_status": "Thumbnailed"
            }
        )
        return {"status": "success", "thumbnail_url": thumb_url}
    except Exception as e:
        logger.error(
            f"Media thumbnail generation failed: {str(e)}",
            extra={
                "organization_id": organization_id,
                "media_id": media_id
            }
        )
        db.rollback()
        raise e
    finally:
        db.close()


async def _cleanup_deleted_media_async() -> dict:
    import os
    import logging
    from app.models.post_media import PostMedia
    from app.storage.factory import StorageProviderFactory

    logger = logging.getLogger(__name__)
    db = SessionLocal()
    try:
        deleted_medias = db.query(PostMedia).filter(
            PostMedia.is_deleted == True,
            PostMedia.upload_status != "FullyDeleted"
        ).limit(100).all()
        
        cleaned_count = 0
        for media in deleted_medias:
            try:
                storage_provider = StorageProviderFactory.get_provider(media.storage_provider)
                
                # Delete original file
                try:
                    await storage_provider.delete_file(media.storage_key)
                except Exception:
                    pass
                    
                # Delete optimized file if exists
                if media.optimized_url:
                    base, ext = os.path.splitext(media.storage_key)
                    opt_key = f"{base}_optimized{ext}"
                    try:
                        await storage_provider.delete_file(opt_key)
                    except Exception:
                        pass
                        
                # Delete thumbnail file if exists
                if media.thumbnail_url:
                    base, ext = os.path.splitext(media.storage_key)
                    thumb_key = f"{base}_thumb{ext}"
                    try:
                        await storage_provider.delete_file(thumb_key)
                    except Exception:
                        pass
                
                media.upload_status = "FullyDeleted"
                db.flush()
                cleaned_count += 1
            except Exception as e:
                logger.error(f"Failed to clean up storage for media {media.id}: {str(e)}")
                
        db.commit()
        return {"status": "success", "cleaned_count": cleaned_count}
    except Exception as e:
        logger.error(f"Cleanup deleted media task failed: {str(e)}")
        db.rollback()
        raise e
    finally:
        db.close()


@shared_task(bind=True, name="app.tasks.optimize_media_task", max_retries=3)
def optimize_media_task(self, media_id: int, organization_id: int) -> dict:
    """
    Async Celery task to optimize/compress and resize original media upload.
    Capping longest edge to 2048px and saving as quality=85 format-specific bytes.
    """
    return run_async(_optimize_media_async(media_id, organization_id))


@shared_task(bind=True, name="app.tasks.generate_thumbnail_task", max_retries=3)
def generate_thumbnail_task(self, media_id: int, organization_id: int) -> dict:
    """
    Async Celery task to generate a 300x300 pixel crop/scale thumbnail of original media upload.
    """
    return run_async(_generate_thumbnail_async(media_id, organization_id))


@shared_task(name="app.tasks.cleanup_deleted_media_task")
def cleanup_deleted_media_task() -> dict:
    """
    Periodic task to physically delete blobs of soft-deleted media files from storage.
    """
    return run_async(_cleanup_deleted_media_async())


@shared_task(name="app.tasks.check_scheduled_posts_task")
def check_scheduled_posts_task() -> dict:
    """
    Celery periodic beat task to poll and publish due scheduled posts.
    """
    import datetime
    import logging
    from app.db.session import SessionLocal
    from app.models.post import Post
    from app.models.campaign import Campaign
    from app.models.publish_job import PublishJob
    from app.constants.posts import PostStatus, CampaignStatus, PublishJobStatus
    import redis
    from app.core.config import settings

    logger = logging.getLogger(__name__)
    db = SessionLocal()
    r = redis.Redis.from_url(settings.REDIS_URL, socket_timeout=5, socket_connect_timeout=5)
    
    now = datetime.datetime.now(datetime.timezone.utc)
    now = datetime.datetime.now(datetime.timezone.utc)
    due_post_ids = [p.id for p in db.query(Post.id).filter(
        Post.status == PostStatus.SCHEDULED.value,
        Post.scheduled_at <= now
    ).all()]
    
    processed_count = 0
    
    for post_id in due_post_ids:
        try:
            post = db.query(Post).filter(Post.id == post_id).with_for_update(skip_locked=True).first()
            if not post or post.status != PostStatus.SCHEDULED.value:
                db.rollback()
                continue
                
            logger.info(f"Processing scheduled post {post.id} (due at {post.scheduled_at})")
            
            post.status = PostStatus.APPROVED.value
            tasks_to_dispatch = []
            
            if post.campaign_id:
                campaign = db.query(Campaign).filter(Campaign.id == post.campaign_id).first()
                if campaign:
                    jobs = db.query(PublishJob).filter(PublishJob.campaign_id == campaign.id).all()
                    job_ids = [job.id for job in jobs]
                    
                    if job_ids:
                        campaign.status = CampaignStatus.PROCESSING.value
                        
                        chunk_size = 50
                        shards = [job_ids[i:i + chunk_size] for i in range(0, len(job_ids), chunk_size)]
                        
                        r.set(f"campaign:{campaign.id}:pending_shards", len(shards))
                        r.set(f"campaign:{campaign.id}:status", "Processing")
                        
                        from app.tasks import process_campaign_shard_task
                        for shard in shards:
                            tasks_to_dispatch.append((process_campaign_shard_task, (shard, post.organization_id, campaign.id)))
                    else:
                        from app.models.location import Location
                        locs = db.query(Location).filter(Location.organization_id == post.organization_id).all()
                        loc_ids = [l.id for l in locs]
                        
                        if loc_ids:
                            campaign.status = CampaignStatus.QUEUED.value
                            from app.tasks import orchestrate_campaign_task
                            tasks_to_dispatch.append((orchestrate_campaign_task, (campaign.id, post.organization_id, loc_ids, post.created_by_user_id)))
                        else:
                            campaign.status = CampaignStatus.FAILED.value
            else:
                from app.models.location import Location
                loc = db.query(Location).filter(Location.organization_id == post.organization_id).first()
                if loc:
                    job = PublishJob(
                        organization_id=post.organization_id,
                        post_id=post.id,
                        location_id=loc.id,
                        provider="gbp",
                        status=PublishJobStatus.PENDING.value
                    )
                    db.add(job)
                    db.flush() # Populate job.id
                    
                    from app.tasks import process_publish_job_task
                    tasks_to_dispatch.append((process_publish_job_task, (job.id, post.organization_id)))
            
            # Stage all database updates/inserts
            db.flush()
            
            # Dispatch all Celery tasks. If Redis is down, this will throw an exception.
            for task_fn, args in tasks_to_dispatch:
                task_fn.delay(*args)
                
            # Celery dispatch succeeded, now commit database transaction safely
            db.commit()
            processed_count += 1
        except Exception as post_err:
            logger.error(f"Failed to process scheduled post {post_id}: {str(post_err)}")
            db.rollback()
            
    db.close()
    return {"status": "success", "processed_count": processed_count}

@shared_task(bind=True, name="app.tasks.publish_listing_edit_task", max_retries=3)
def publish_listing_edit_task(self, edit_id: int, organization_id: int) -> dict:
    import redis
    import logging
    import httpx
    import asyncio
    from app.core.config import settings
    from app.core.listing_fields import FIELD_MAP
    from app.db.session import SessionLocal
    from sqlalchemy.orm import Session
    from app.services.listing_edit_service import ListingEditService
    from app.services.payload_transformers import PayloadTransformer
    from app.models.location_edit import LocationEdit
    from app.models.location import Location
    from app.providers.factory import ProviderFactory
    from app.providers.gbp.auth import PermanentAuthError
    
    logger = logging.getLogger(__name__)
    
    r = redis.Redis.from_url(settings.REDIS_URL, socket_timeout=5, socket_connect_timeout=5)
    lock_key = f"lock:publish_edit:{edit_id}"
    lock = r.lock(lock_key, timeout=120)
    
    if not lock.acquire(blocking=False):
        return {"status": "skipped", "reason": "Edit is currently being published by another worker"}
        
    db = SessionLocal()
    try:
        edit = db.query(LocationEdit).filter(
            LocationEdit.id == edit_id,
            LocationEdit.organization_id == organization_id
        ).first()
        
        if not edit:
            return {"status": "skipped", "reason": "Edit not found"}
            
        if edit.status == "Published" or edit.published_at is not None:
            return {"status": "skipped", "reason": "Idempotency guard: Edit is already published"}
            
        if edit.status != "Publishing":
            return {"status": "skipped", "reason": f"Edit not in Publishing state: {edit.status}"}

        location = db.query(Location).filter(Location.id == edit.location_id).first()
        if not location:
            raise Exception("Location not found.")
            
        edit.publish_attempts += 1
        db.commit()
        
        gbp_payload = PayloadTransformer.to_gbp_payload(edit.field_name, edit.new_value)
        update_mask = FIELD_MAP[edit.field_name].gbp_field_mask
        
        provider = ProviderFactory.get_provider("gbp", organization_id, db)
        
        try:
            res = run_async(provider.patch_location(location.google_location_id, gbp_payload, update_mask))
            ListingEditService.mark_published(db, edit_id=edit.id, organization_id=organization_id)
            db.commit()
            return {"status": "completed"}
            
        except Exception as e:
            logger.error(f"PublishListingEdit {edit_id} failed: {str(e)}")
            is_retryable = True
            google_error_code = None
            
            if isinstance(e, PermanentAuthError):
                is_retryable = False
                google_error_code = "AUTH_REVOKED"
            elif isinstance(e, httpx.HTTPStatusError):
                if e.response.status_code in [400, 401, 403, 404, 409]:
                    is_retryable = False
                google_error_code = str(e.response.status_code)
            elif not isinstance(e, (httpx.RequestError, TimeoutError, ConnectionError)):
                is_retryable = False
                
            if is_retryable and self.request.retries < self.max_retries:
                # Let celery handle retry; leave it in Publishing state
                countdown = 60 * (2 ** self.request.retries)
                db.close()
                raise self.retry(exc=e, countdown=countdown)
            else:
                ListingEditService.mark_failed(
                    db,
                    edit_id=edit.id,
                    organization_id=organization_id,
                    failure_reason=str(e),
                    google_error_code=google_error_code
                )
                db.commit()
                return {"status": "failed", "reason": str(e)}
                
    finally:
        try:
            lock.release()
        except Exception:
            pass
        db.close()

@shared_task(name="app.tasks.archive_old_activity_logs_task")
def archive_old_activity_logs_task() -> dict:
    from app.db.session import SessionLocal
    from datetime import datetime, timezone, timedelta
    from app.models.activity_log import ActivityLog
    from app.models.activity_log_archive import ActivityLogArchive
    
    db = SessionLocal()
    cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    
    try:
        # We process in batches to avoid locking the table for too long
        batch_size = 500
        total_archived = 0
        
        while True:
            # Find old logs
            old_logs = db.query(ActivityLog).filter(
                ActivityLog.created_at < cutoff
            ).limit(batch_size).all()
            
            if not old_logs:
                break
                
            # Create archive copies
            from sqlalchemy.dialects.postgresql import insert
            
            archive_data = []
            for log in old_logs:
                archive_data.append({
                    "id": log.id,
                    "organization_id": log.organization_id,
                    "location_id": log.location_id,
                    "actor_user_id": log.actor_user_id,
                    "entity_type": log.entity_type,
                    "entity_id": log.entity_id,
                    "action": log.action,
                    "payload": log.payload,
                    "correlation_id": log.correlation_id,
                    "created_at": log.created_at
                })
            
            if archive_data:
                stmt = insert(ActivityLogArchive).values(archive_data)
                stmt = stmt.on_conflict_do_nothing(index_elements=['id'])
                db.execute(stmt)
            
            # Delete originals
            log_ids = [l.id for l in old_logs]
            db.query(ActivityLog).filter(ActivityLog.id.in_(log_ids)).delete(synchronize_session=False)
            
            db.commit()
            total_archived += len(old_logs)
            
        return {"status": "success", "archived_count": total_archived}
        
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()

@shared_task(name="app.tasks.sync_insights_task")
def sync_insights_task(location_id: int, start_date_str: str, end_date_str: str, run_type: str = "Scheduled") -> dict:
    """
    Celery task to synchronize daily performance insights for a location.
    Enforces Redis locking to prevent concurrent synchronizations.
    """
    import redis
    import datetime
    import logging
    from app.core.config import settings
    from app.services.insight_sync_service import InsightSyncService

    logger = logging.getLogger(__name__)
    logger.info(f"Starting sync_insights_task for location_id={location_id}, range={start_date_str} to {end_date_str}, type={run_type}")
    
    db: Session = SessionLocal()
    try:
        location = db.query(Location).filter(Location.id == location_id).first()
        if not location:
            logger.error(f"Location {location_id} not found for insights sync")
            return {"status": "error", "reason": f"Location {location_id} not found"}

        organization_id = location.organization_id
        try:
            start_date = datetime.date.fromisoformat(start_date_str)
            end_date = datetime.date.fromisoformat(end_date_str)
        except ValueError as date_err:
            logger.error(f"Invalid date format for insights sync: {date_err}")
            return {"status": "error", "reason": f"Invalid date format: {date_err}"}

        r = redis.Redis.from_url(settings.REDIS_URL, socket_timeout=5, socket_connect_timeout=5)
        lock_key = f"lock:sync_insights:{organization_id}:{location_id}"
        lock = r.lock(lock_key, timeout=300)

        if not lock.acquire(blocking=False):
            logger.warning(f"Skipping insights sync for location {location_id}: lock already held")
            return {"status": "skipped", "reason": "insights sync already in progress"}

        try:
            logger.info(f"Executing InsightSyncService for location {location_id}...")
            # Import and run async function inside Celery worker thread
            res_msg = run_async(InsightSyncService.sync_location_insights(
                db=db,
                location_id=location_id,
                start_date=start_date,
                end_date=end_date,
                run_type=run_type
            ))
            logger.info(f"Insights sync completed for location {location_id}: {res_msg}")
            return {"status": "success", "message": res_msg}
        finally:
            try:
                lock.release()
            except Exception:
                pass
    except Exception as e:
        import logging
        logging.error(f"Failed sync_insights_task for location {location_id}: {str(e)}")
        return {"status": "failed", "reason": str(e)}
    finally:
        db.close()

@shared_task(name="app.tasks.evaluate_attention_flags_task")
def evaluate_attention_flags_task(organization_id: int) -> dict:
    """
    Celery task to evaluate reputation and performance attention flags for an organization.
    """
    import redis
    from app.core.config import settings
    from app.services.insight_sync_service import InsightSyncService

    db: Session = SessionLocal()
    try:
        r = redis.Redis.from_url(settings.REDIS_URL, socket_timeout=5, socket_connect_timeout=5)
        lock_key = f"lock:attention_eval:{organization_id}"
        lock = r.lock(lock_key, timeout=300)

        if not lock.acquire(blocking=False):
            return {"status": "skipped", "reason": "attention evaluation already in progress"}

        try:
            InsightSyncService.evaluate_attention_flags(db, organization_id)
            return {"status": "success"}
        finally:
            try:
                lock.release()
            except Exception:
                pass
    except Exception as e:
        import logging
        logging.error(f"Failed evaluate_attention_flags_task for org {organization_id}: {str(e)}")
        return {"status": "failed", "reason": str(e)}
    finally:
        db.close()

@shared_task(name="app.tasks.sync_organization_insights_task")
def sync_organization_insights_task(organization_id: int, start_date_str: str, end_date_str: str, run_type: str = "Scheduled", force: bool = False) -> dict:
    """
    Celery task to orchestrate insights synchronization for an entire organization.
    Uses organization-level Redis lock and OrganizationSyncState.
    """
    import redis
    import datetime
    import logging
    from app.core.config import settings
    from app.models.organization_sync_state import OrganizationSyncState
    from app.models.location import Location

    logger = logging.getLogger(__name__)
    logger.info(f"Starting sync_organization_insights_task for org={organization_id}, force={force}")

    db: Session = SessionLocal()
    r = redis.Redis.from_url(settings.REDIS_URL, socket_timeout=5, socket_connect_timeout=5)
    lock_key = f"insights_sync:org_{organization_id}"
    lock = r.lock(lock_key, timeout=3600)  # 1 hour lease

    try:
        # Acquire lock first before database state mutations
        if not lock.acquire(blocking=False):
            logger.warning(f"Skipping organization insights sync for org={organization_id}: Redis lock already held")
            return {"status": "skipped", "reason": "sync already in progress"}

        try:
            # Upsert sync state inside the lock
            sync_state = db.query(OrganizationSyncState).filter(
                OrganizationSyncState.organization_id == organization_id
            ).first()
            if not sync_state:
                sync_state = OrganizationSyncState(
                    organization_id=organization_id,
                    insights_sync_in_progress=True,
                    last_insights_sync_started_at=datetime.datetime.now(datetime.timezone.utc),
                    last_insights_sync_status="in_progress"
                )
                db.add(sync_state)
            else:
                sync_state.insights_sync_in_progress = True
                sync_state.last_insights_sync_started_at = datetime.datetime.now(datetime.timezone.utc)
                sync_state.last_insights_sync_status = "in_progress"
                sync_state.last_insights_sync_error = None
            db.commit()

            # Query all active locations
            locations = db.query(Location).filter(
                Location.organization_id == organization_id,
                Location.sync_status != "Failed"
            ).all()

            logger.info(f"Syncing insights for {len(locations)} locations in org={organization_id}")
            errors = []
            for loc in locations:
                try:
                    # Queue the task asynchronously
                    sync_insights_task.delay(
                        location_id=loc.id,
                        start_date_str=start_date_str,
                        end_date_str=end_date_str,
                        run_type=run_type
                    )
                except Exception as ex:
                    errors.append(f"Location {loc.id}: {str(ex)}")

            # Update final state inside the lock
            sync_state = db.query(OrganizationSyncState).filter(
                OrganizationSyncState.organization_id == organization_id
            ).first()

            if errors:
                sync_state.insights_sync_in_progress = False
                sync_state.last_insights_sync_status = "failed"
                sync_state.last_insights_sync_error = "; ".join(errors)
            else:
                now_time = datetime.datetime.now(datetime.timezone.utc)
                sync_state.insights_sync_in_progress = False
                sync_state.last_insights_sync_status = "success"
                sync_state.last_insights_sync_at = now_time
                sync_state.last_insights_sync_completed_at = now_time
                sync_state.last_insights_sync_error = None

            db.commit()

            # Trigger flags evaluation
            try:
                from app.services.insight_sync_service import InsightSyncService
                InsightSyncService.evaluate_attention_flags(db, organization_id)
            except Exception as flag_ex:
                logger.error(f"Failed to evaluate attention flags for org={organization_id}: {str(flag_ex)}")

            return {"status": "success", "errors": errors}
        finally:
            try:
                lock.release()
            except Exception:
                pass
    except Exception as e:
        logger.error(f"General error in sync_organization_insights_task for org={organization_id}: {str(e)}")
        # Attempt fallback status update
        try:
            sync_state = db.query(OrganizationSyncState).filter(
                OrganizationSyncState.organization_id == organization_id
            ).first()
            if sync_state:
                sync_state.insights_sync_in_progress = False
                sync_state.last_insights_sync_status = "failed"
                sync_state.last_insights_sync_error = str(e)
                db.commit()
        except Exception:
            pass
        return {"status": "failed", "reason": str(e)}
    finally:
        db.close()


@shared_task(name="app.tasks.sync_all_insights_beat_task")
def sync_all_insights_beat_task() -> dict:
    """
    Nightly Celery beat task to sync insights incrementally for all active locations
    """
    import datetime
    from app.models.organization import Organization
    db: Session = SessionLocal()
    try:
        orgs = db.query(Organization).all()
        today = datetime.date.today()
        yesterday = today - datetime.timedelta(days=1)
        start_date = today - datetime.timedelta(days=7)
        
        enqueued_count = 0
        for org in orgs:
            sync_organization_insights_task.delay(
                organization_id=org.id,
                start_date_str=start_date.isoformat(),
                end_date_str=yesterday.isoformat(),
                run_type="Scheduled"
            )
            enqueued_count += 1
            
        return {"status": "success", "triggered_orgs": enqueued_count}
    except Exception as e:
        import logging
        logging.error(f"Failed sync_all_insights_beat_task: {str(e)}")
        raise e
    finally:
        db.close()

@shared_task(name="app.tasks.retry_failed_sentiment_beat_task")
def retry_failed_sentiment_beat_task() -> dict:
    """
    Periodic beat task to find any reviews that missed their event-driven sentiment tagging 
    (e.g., worker crashed or LLM timed out) and enqueue them.
    """
    from app.db.session import SessionLocal
    from app.models.review import Review
    import logging
    
    db = SessionLocal()
    try:
        # Find locations with untagged reviews
        untagged_locations = db.query(Review.location_id, Review.organization_id).filter(
            Review.sentiment_tagged_at == None,
            Review.is_deleted == False
        ).distinct().all()

        enqueued = 0
        for loc_id, org_id in untagged_locations:
            tag_reviews_sentiment_task.delay(loc_id, org_id)
            enqueued += 1

        return {"status": "success", "enqueued_locations": enqueued}
    except Exception as e:
        logging.error(f"Failed retry_failed_sentiment_beat_task: {str(e)}")
        raise e
    finally:
        db.close()

@shared_task(name="app.tasks.sync_gbp_attributes_metadata_task")
def sync_gbp_attributes_metadata_task(category_id: str, region_code: str, language_code: str, organization_id: int) -> dict:
    from app.db.session import SessionLocal
    from app.services.attribute_sync_service import AttributeSyncService
    import asyncio
    db = SessionLocal()
    try:
        service = AttributeSyncService(db)
        run_async(service.sync_category_metadata(organization_id, category_id, region_code, language_code))
        return {"status": "success", "category_id": category_id}
    except Exception as e:
        import logging
        logging.error(f"sync_gbp_attributes_metadata_task failed: {e}")
        raise e
    finally:
        db.close()

@shared_task(name="app.tasks.sync_all_active_categories_metadata_task")
def sync_all_active_categories_metadata_task() -> dict:
    from app.db.session import SessionLocal
    from app.models.location import Location
    import logging
    db = SessionLocal()
    try:
        locations = db.query(Location.google_category_resource_name, Location.organization_id).filter(
            Location.google_category_resource_name != None
        ).distinct().all()
        
        region_code = "IN"
        language_code = "en"
        enqueued_count = 0
        
        for category_resource_name, org_id in locations:
            if not category_resource_name:
                continue
            category_id = category_resource_name.replace("categories/", "")
            sync_gbp_attributes_metadata_task.delay(category_id, region_code, language_code, org_id)
            enqueued_count += 1
            
        return {"status": "success", "enqueued_count": enqueued_count}
    except Exception as e:
        logging.error(f"sync_all_active_categories_metadata_task failed: {e}")
        raise e
    finally:
        db.close()

@shared_task(name="app.tasks.sync_location_attributes_task")
def sync_location_attributes_task(location_id: int) -> dict:
    from app.db.session import SessionLocal
    from app.services.attribute_sync_service import AttributeSyncService
    import asyncio
    db = SessionLocal()
    try:
        service = AttributeSyncService(db)
        run_async(service.fetch_location_attributes(location_id))
        return {"status": "success", "location_id": location_id}
    except Exception as e:
        import logging
        logging.error(f"sync_location_attributes_task failed: {e}")
        raise e
    finally:
        db.close()

@shared_task(name="app.tasks.backfill_google_category_resource_names_task")
def backfill_google_category_resource_names_task() -> dict:
    from app.db.session import SessionLocal
    from app.models.location import Location
    from app.providers.factory import ProviderFactory
    import asyncio
    import logging
    
    db = SessionLocal()
    try:
        locations = db.query(Location).filter(
            Location.google_category_resource_name.is_(None),
            Location.google_location_id.is_not(None)
        ).all()
        
        updated = 0
        for loc in locations:
            try:
                provider = ProviderFactory.get_provider("gbp", loc.organization_id, db)
                data = run_async(provider.get_location(loc.google_location_id))
                
                categories = data.get("categories", {})
                primary = categories.get("primaryCategory", {})
                resource_name = primary.get("name")
                
                if resource_name:
                    loc.google_category_resource_name = resource_name
                    db.commit()
                    updated += 1
            except Exception as e:
                logging.error(f"Backfill failed for location {loc.id}: {e}")
                
        return {"status": "success", "updated_count": updated}
    finally:
        db.close()

@shared_task(name="app.tasks.publish_location_attributes_task", max_retries=3)
def publish_location_attributes_task(location_id: int) -> dict:
    from app.db.session import SessionLocal
    from app.models.location import Location
    from app.models.user import User
    from app.models.oauth_account import OAuthAccount
    from app.models.gbp_location_attribute_rejection import GbpLocationAttributeRejection
    from app.providers.gbp.auth import GBPAuthManager
    from app.providers.base.auth import AuthContext
    from app.providers.gbp.client import GBPAsyncClient
    from app.providers.base.exceptions import ProviderError
    from app.providers.factory import ProviderFactory
    from sqlalchemy.dialects.postgresql import insert
    import datetime
    import hashlib
    import json
    import asyncio
    import logging
    import re
    
    logger = logging.getLogger(__name__)
    db = SessionLocal()
    
    try:
        location = db.query(Location).filter(Location.id == location_id).first()
        if not location:
            return {"status": "error", "reason": "Location not found"}
            
        if not location.google_location_id:
            location.sync_status = "Failed"
            db.commit()
            return {"status": "error", "reason": "Location is not linked to Google"}
            
        draft_attrs = location.draft_attributes or []
        
        current_draft_hash = None
        if draft_attrs:
            current_draft_hash = hashlib.sha256(json.dumps(draft_attrs, sort_keys=True).encode()).hexdigest()
            
        if not draft_attrs:
            location.sync_status = "Synced"
            db.commit()
            return {"status": "success", "message": "Attributes are up to date"}
            
        # Get rejection capability memory (sliding 30-day window to allow for Google feature rollouts)
        expiry_limit = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30)
        rejections = db.query(GbpLocationAttributeRejection).filter(
            GbpLocationAttributeRejection.location_id == location_id,
            GbpLocationAttributeRejection.last_seen >= expiry_limit,
            GbpLocationAttributeRejection.suppressed == False
        ).all()
        rejected_ids = {r.attribute_id for r in rejections}
        
        # Clean draft attributes based on existing rejection memory (proactive filtering)
        pre_cleaned_drafts = [attr for attr in draft_attrs if attr["name"] not in rejected_ids]
        removed_due_to_memory = [attr["name"] for attr in draft_attrs if attr["name"] in rejected_ids]
        
        if removed_due_to_memory:
            logger.info("attributes_removed_due_to_memory", extra={
                "location_id": location_id,
                "removed_attributes": removed_due_to_memory
            })
        
        current_payload_attrs = pre_cleaned_drafts
        
        # Publish to Google API
        oauth_account = db.query(OAuthAccount).join(User).filter(
            User.organization_id == location.organization_id,
            User.role.in_(["Owner", "Admin"]),
            OAuthAccount.provider.in_(["gbp", "google"])
        ).first()

        if not oauth_account:
            location.sync_status = "Failed"
            location.attention_needed = True
            location.attention_reason = "Google credentials not found for organization"
            db.commit()
            return {"status": "error", "reason": "Google credentials not found for organization"}

        auth_context = AuthContext(
            organization_id=location.organization_id,
            access_token=decrypt_token(oauth_account.access_token),
            refresh_token=decrypt_token(oauth_account.refresh_token) if oauth_account.refresh_token else None,
            expires_at=oauth_account.expires_at
        )
        auth_manager = GBPAuthManager(auth_context, db)
        
        async def _do_publish(payload_attrs):
            access_token = await auth_manager.get_valid_token()
            
            if "mock_access_token" in access_token:
                return True, None, None
                
            headers = {"Authorization": f"Bearer {access_token}"}
            url = f"https://mybusinessbusinessinformation.googleapis.com/v1/{location.google_location_id}/attributes"
            
            payload = {
                "name": f"{location.google_location_id}/attributes",
                "attributes": payload_attrs
            }
            
            logger.debug("Publishing to Google: loc=%s", location_id)
            
            attribute_mask = ",".join(attr["name"] for attr in payload_attrs) if payload_attrs else ""
            
            async with GBPAsyncClient(location.organization_id) as client:
                try:
                    resp = await client.request("PATCH", url, headers=headers, json=payload, params={"attributeMask": attribute_mask})
                    if resp.status_code != 200:
                        logger.error(f"attribute_publish_failed: loc={location_id} status={resp.status_code} body={resp.text}")
                        return False, resp, None
                    return True, resp, None
                except ProviderError as e:
                    logger.error(f"attribute_publish_provider_error: loc={location_id} status={e.status_code} detail={e.detail}")
                    return False, None, e
                
        success = False
        response = None
        exception = None
        removed_on_this_run = []
        
        if current_payload_attrs:
            success, response, exception = run_async(_do_publish(current_payload_attrs))

            if not success:
                invalid_names = []
                error_data = None

                # Parse error body from HTTP response or ProviderError detail string
                if response is not None:
                    try:
                        error_data = response.json()
                    except Exception:
                        pass
                elif exception is not None:
                    try:
                        # ProviderError puts response text in the detail string, e.g., "Validation error: {...}"
                        match = re.search(r'(\{.*\})', exception.detail, re.DOTALL)
                        if match:
                            error_data = json.loads(match.group(1))
                    except Exception:
                        pass

                if error_data is not None:
                    try:
                        details = error_data.get("error", {}).get("details", [])
                        for detail in details:
                            # Path 1: ErrorInfo envelope (New Google shape)
                            if detail.get("@type") == "type.googleapis.com/google.rpc.ErrorInfo":
                                reason = detail.get("reason", "INVALID_ARGUMENT")
                                metadata = detail.get("metadata", {})
                                
                                # Single attribute name
                                if "attribute_name" in metadata:
                                    invalid_names.append({"name": metadata["attribute_name"], "reason": reason})
                                # Multiple attribute names
                                elif "attribute_names" in metadata:
                                    names = metadata["attribute_names"].split(",")
                                    for n in names:
                                        if n.strip():
                                            invalid_names.append({"name": n.strip(), "reason": reason})

                            # Path 2: custom metadata envelope with attribute_names
                            elif "metadata" in detail and "attribute_names" in detail.get("metadata", {}):
                                names = detail["metadata"]["attribute_names"].split(",")
                                invalid_names.extend([{"name": n.strip(), "reason": "INVALID_ATTRIBUTE_NAME"} for n in names if n.strip()])
                            
                            # Path 3: standard BadRequest fieldViolations
                            elif detail.get("@type") == "type.googleapis.com/google.rpc.BadRequest":
                                for violation in detail.get("fieldViolations", []):
                                    field_name = violation.get("field", "")
                                    if "attributes[" in field_name:
                                        match = re.search(r'attributes\["([^"]+)"\]', field_name)
                                        if match:
                                            invalid_names.append({"name": match.group(1), "reason": "INVALID_ARGUMENT"})
                    except Exception as parse_exc:
                        logger.warning(
                            "google_error_parse_failed",
                            extra={"location_id": location_id, "error": str(parse_exc), "error_data": str(error_data)[:500]}
                        )

                # M2: If error_data was present but we couldn't extract any attribute names,
                # attempt a fuzzy match based on the error reason
                if error_data is not None and not invalid_names:
                    reason = "INVALID_ARGUMENT"
                    try:
                        reason = error_data.get("error", {}).get("details", [{}])[0].get("reason", "INVALID_ARGUMENT")
                    except Exception:
                        pass

                    if "SOCIAL_MEDIA" in reason:
                        # Guess which ones are social media
                        social_ids = [a["name"] for a in current_payload_attrs if any(x in a["name"] for x in ["facebook", "instagram", "twitter", "linkedin", "youtube", "pinterest"])]
                        if social_ids:
                            invalid_names.extend([{"name": sid, "reason": reason} for sid in social_ids])
                    
                    # If still no names, we must fail all in this batch to prevent infinite loop
                    if not invalid_names:
                        logger.warning(
                            "google_error_no_invalid_attrs_extracted",
                            extra={"location_id": location_id, "error_data": str(error_data)[:1000]}
                        )
                        invalid_names.extend([{"name": a["name"], "reason": reason} for a in current_payload_attrs])

                if invalid_names:
                    # Add to persistent rejection memory using atomic upsert.
                    # C2: If this fails we must stop — continuing would retry the same bad attributes indefinitely.
                    rejection_upsert_failed = False
                    for invalid_name_item in invalid_names:
                        attr_id = invalid_name_item.get("name") if isinstance(invalid_name_item, dict) else invalid_name_item
                        rejection_reason = invalid_name_item.get("reason", "INVALID_ATTRIBUTE_NAME") if isinstance(invalid_name_item, dict) else "INVALID_ATTRIBUTE_NAME"
                        
                        # Try to find the value we tried to send
                        rejected_val = None
                        for original_attr in current_payload_attrs:
                            if original_attr["name"] == attr_id:
                                rejected_val = original_attr
                                break

                        stmt = insert(GbpLocationAttributeRejection).values(
                            location_id=location_id,
                            attribute_id=attr_id,
                            rejection_reason=rejection_reason,
                            rejected_value=rejected_val,
                            first_seen=datetime.datetime.now(datetime.timezone.utc),
                            last_seen=datetime.datetime.now(datetime.timezone.utc),
                            rejection_count=1,
                            suppressed=False
                        )
                        stmt = stmt.on_conflict_do_update(
                            index_elements=['location_id', 'attribute_id'],
                            set_={
                                'rejection_count': GbpLocationAttributeRejection.rejection_count + 1,
                                'last_seen': datetime.datetime.now(datetime.timezone.utc),
                                'rejection_reason': rejection_reason,
                                'rejected_value': rejected_val
                            }
                        )
                        try:
                            db.execute(stmt)
                            removed_on_this_run.append(attr_id)
                        except Exception as upsert_exc:
                            db.rollback()
                            logger.error(
                                "rejection_upsert_failed",
                                extra={"location_id": location_id, "attribute_id": attr_id, "error": str(upsert_exc)}
                            )
                            rejection_upsert_failed = True
                            break

                    if rejection_upsert_failed:
                        location.sync_status = "Failed"
                        db.commit()
                        return {"status": "error", "reason": "Failed to record attribute rejection — publish aborted."}

                    db.commit()

                    # Strip only the newly rejected attributes
                    current_payload_attrs = [attr for attr in current_payload_attrs if attr["name"] not in removed_on_this_run]

                    # Persist the cleaned draft state
                    try:
                        location.draft_attributes = current_payload_attrs
                        db.commit()
                    except Exception as e:
                        db.rollback()
                        logger.error("cleaned_draft_save_failed", extra={"location_id": location_id, "error": str(e)})

                    # Retry PATCH exactly ONCE using cleaned payload
                    if current_payload_attrs:
                        success, response, exception = run_async(_do_publish(current_payload_attrs))
                    else:
                        success = True
                        response = None
                        exception = None
                else:
                    # Other type of Google error
                    location.sync_status = "Failed"
                    db.commit()
                    if exception is not None:
                        return {"status": "error", "reason": exception.detail}
                    elif response is not None:
                        return {"status": "error", "reason": f"Failed to publish attributes: {response.text}"}
                    else:
                        return {"status": "error", "reason": "Failed to publish attributes"}
        else:
            # If all attributes were already pre-filtered out by capability memory
            success = True
            response = None
            exception = None
            
        if not success:
            location.sync_status = "Failed"
            db.commit()
            if exception is not None:
                return {"status": "error", "reason": exception.detail}
            elif response is not None:
                return {"status": "error", "reason": f"Failed to publish attributes on retry: {response.text}"}
            else:
                return {"status": "error", "reason": "Failed to publish attributes on retry"}
            
        # Successfully published. Update google_attributes in database
        all_removed = list(set(removed_due_to_memory + removed_on_this_run))
        try:
            provider = ProviderFactory.get_provider("gbp", location.organization_id, db)
            updated_data = run_async(provider.get_location_attributes(location.google_location_id))
            location.google_attributes = updated_data.get("attributes", [])
            location.google_attributes_stale = False
        except Exception as e:
            logger.warning(f"Failed to refetch attributes after publish for {location_id}: {e}")
            # Fallback to optimistic update
            google_dict = {a.get("name"): a for a in (location.google_attributes or [])}
            for draft in current_payload_attrs:
                google_dict[draft["name"]] = draft
                
            for r_id in all_removed:
                if r_id in google_dict:
                    del google_dict[r_id]
                    
            location.google_attributes = list(google_dict.values())
            location.google_attributes_stale = True

        # C3: Cleanup is critical — if it fails the client will believe publish succeeded but draft
        # was never cleared, causing duplicate publishes on every subsequent call.
        try:
            location.draft_attributes = []  # Clear draft since it is successfully published
            location.last_google_sync = datetime.datetime.now(datetime.timezone.utc)
            location.last_published_at = datetime.datetime.now(datetime.timezone.utc)
            if current_draft_hash:
                location.last_publish_hash = current_draft_hash
            location.sync_status = "Synced"
            location.attention_needed = False
            location.attention_reason = None
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error("publish_cleanup_failed", extra={"location_id": location_id, "error": str(e)})
            return {"status": "error", "reason": "Attributes were published to Google but the local state could not be updated."}
        
        return {"status": "success", "removed_attributes": all_removed}

    except Exception as e:
        logger.error(f"publish_location_attributes_task failed: {e}")
        db.rollback()
        raise e
    finally:
        db.close()

