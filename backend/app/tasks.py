import datetime
import random
from datetime import timezone
from celery import shared_task
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.user import User
from app.core.roles import ADMIN_ROLES
from app.models.organization import Organization
from app.models.oauth_account import OAuthAccount
from app.models.location import Location
from app.models.sync_log import SyncLog
from app.core.security import decrypt_token, encrypt_token
from app.providers.factory import ProviderFactory
from app.providers.base.exceptions import ProviderAuthError
from app.services.review_sync_service import ReviewSyncService
from app.core import plan_config
from app.core.redis_client import get_redis as _get_redis
import asyncio

def run_async(coro):
    """
    Run an async coroutine synchronously.
    Uses asyncio.run() to ensure thread safety across Celery workers.
    """
    return asyncio.run(coro)


def _is_retryable_publish_error(e) -> bool:
    """Auth failures, 4xx client errors, and logic/system exceptions are permanent;
    network/timeout errors and non-4xx HTTP errors are worth retrying."""
    import httpx
    from app.providers.gbp.auth import PermanentAuthError
    if isinstance(e, PermanentAuthError):
        return False
    if isinstance(e, httpx.HTTPStatusError):
        return e.response.status_code not in (400, 401, 403, 404, 409)
    return isinstance(e, (httpx.RequestError, TimeoutError, ConnectionError))


def _provider_error_data(e) -> dict:
    """Best-effort structured body from a failed provider HTTP call."""
    import httpx
    if isinstance(e, httpx.HTTPStatusError):
        try:
            return e.response.json()
        except Exception:
            return {"raw_response": e.response.text}
    return {}


def _finalize_campaign_if_complete(db, campaign, organization_id):
    """When a campaign's last pending job resolves (total_pending == 0), set its
    terminal status + primary-post status from the published/failed counts and
    write the 'completed' audit log. No-op while jobs are still pending."""
    if not (campaign and campaign.total_pending == 0):
        return
    from app.models.campaign_audit_log import CampaignAuditLog
    from app.constants.posts import PostStatus
    old_status = campaign.status
    if campaign.total_failed == 0:
        new_status = "Completed"
    elif campaign.total_published == 0:
        new_status = "Failed"
    else:
        new_status = "PartiallyCompleted"
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
        log_metadata={"final_stats": {"published": campaign.total_published, "failed": campaign.total_failed}},
    ))


@shared_task(name="app.tasks.run_local_rank_scan_task")
def run_local_rank_scan_task(scan_id: int) -> dict:
    """Run a queued geo-grid local rank scan (N² DataForSEO Maps calls).

    Credits are charged here, AFTER the scan succeeds, so a failed fetch is free.
    Redis-locked per location to stop overlapping scans burning the API twice.
    """
    import logging
    from fastapi import HTTPException
    from app.models.local_rank_scan import LocalRankScan
    from app.services import local_rank_service
    from app.services.billing.credit_service import CreditService

    logger = logging.getLogger(__name__)
    db: Session = SessionLocal()
    try:
        scan = db.query(LocalRankScan).filter(LocalRankScan.id == scan_id).first()
        if not scan:
            return {"status": "error", "reason": "scan not found"}

        location = db.query(Location).filter(Location.id == scan.location_id).first()
        if not location:
            scan.status = "Failed"
            scan.error = "Location not found"
            db.commit()
            return {"status": "error", "reason": "location not found"}

        r = _get_redis()
        lock = r.lock(f"lock:local_rank_scan:{scan.location_id}", timeout=600)
        if not lock.acquire(blocking=False):
            scan.status = "Failed"
            scan.error = "Another scan is already running for this location"
            db.commit()
            return {"status": "skipped", "reason": "scan in progress"}

        try:
            price = local_rank_service.scan_price(scan.grid_size)
            # RESERVE credits BEFORE the expensive N² paid-API scan. The route only
            # prechecks (unlocked read), so without this N concurrent scans sharing one
            # credit could all pass the check and run the real-money work for free. The
            # reserve is atomic under the org row lock; refunded below if the scan fails.
            CreditService.reserve(db, scan.organization_id, price)
            try:
                meta = location.gbp_raw.get("metadata") if isinstance(location.gbp_raw, dict) else None
                business_place_id = meta.get("placeId") if isinstance(meta, dict) else None
                result = run_async(local_rank_service.scan_for_location(
                    latlng=location.latlng, gbp_raw=location.gbp_raw, address=location.address,
                    keyword=scan.keyword, grid_size=scan.grid_size,
                    radius_miles=scan.radius_miles, business_name=location.location_name,
                    business_place_id=business_place_id,
                ))
                scan.cells = result["cells"]
                scan.avg_rank = result["avg_rank"]
                scan.solv = result["solv"]
                scan.found_count = result["found_count"]
                scan.total_cells = result["total_cells"]
                scan.credits_charged = price
                scan.status = "Completed"
                db.add(scan)
                # Free competitor tracking: snapshot tracked competitors from this
                # scan's local-pack results (no extra API spend). Never fail the scan.
                try:
                    from app.services import competitor_service
                    competitor_service.harvest_from_scan(db, scan)
                except Exception:
                    logger.exception("Competitor harvest failed for scan %s", scan_id)
                # Capture the storefront's real coords (from our own result) so future
                # scans centre exactly — only when we don't already have coordinates.
                bc = result.get("business_coords")
                has_latlng = isinstance(location.latlng, dict) and location.latlng.get("latitude") is not None
                if bc and not has_latlng:
                    location.latlng = bc
                    db.add(location)
                db.commit()
            except Exception:
                # Anything after the reserve failed (scan or persist) — give the credits
                # back; a scan that doesn't produce saved results is free.
                db.rollback()
                CreditService.refund(db, scan.organization_id, price)
                raise
            return {"status": "completed", "scan_id": scan_id}
        except HTTPException as he:
            db.rollback()
            scan = db.query(LocalRankScan).filter(LocalRankScan.id == scan_id).first()
            if scan:
                scan.status = "Failed"
                scan.error = str(he.detail)
                db.commit()
            return {"status": "error", "reason": str(he.detail)}
        except Exception as e:
            db.rollback()
            logger.error("Local rank scan %s failed: %s", scan_id, e, exc_info=True)
            scan = db.query(LocalRankScan).filter(LocalRankScan.id == scan_id).first()
            if scan:
                scan.status = "Failed"
                scan.error = str(e)[:500]
                db.commit()
            return {"status": "error", "reason": str(e)}
        finally:
            try:
                lock.release()
            except Exception:
                pass
    finally:
        db.close()

@shared_task(name="app.tasks.sync_reviews_task")
def sync_reviews_task(location_id: int, run_type: str = "Scheduled", user_id: int = None) -> dict:
    """
    Synchronizes reviews for a specific location via the ReviewSyncService.
    """
    import redis
    from app.core.config import settings
    from app.services.billing.entitlement_service import EntitlementService
    
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
        
        org = db.query(Organization).filter(Organization.id == organization_id).first()
        if org and EntitlementService.is_org_locked(org):
            return {"status": "skipped", "reason": "organization is locked"}
        
        r = _get_redis()
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

            # Only revalidate when reviews actually changed — an unconditional bust
            # rewrote this microsite's ISR cache on every scheduled run (Vercel ISR
            # write blowup). Matches the change-gated media/extras syncs.
            if isinstance(result, dict) and result.get("synced_count"):
                from app.services.revalidation_service import trigger_bulk_microsite_revalidation
                trigger_bulk_microsite_revalidation([location_id])

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
    from app.services.billing.entitlement_service import EntitlementService

    logger = logging.getLogger(__name__)
    db: Session = SessionLocal()
    
    org = db.query(Organization).filter(Organization.id == organization_id).first()
    if org and EntitlementService.is_org_locked(org):
        db.close()
        return {"status": "skipped", "reason": "organization is locked"}

    r = _get_redis()

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
                
                # Recalculate health score after review sync completes
                from app.services.health_score_service import HealthScoreService
                HealthScoreService.recalculate_health_score(db, loc_id, reason="review_sync")
                db.commit()

                synced_count = result.get("synced_count", 0) if isinstance(result, dict) else 0
                results.append({"location_id": loc_id, "status": "success", "result": result, "synced_count": synced_count})

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

        # Revalidate only microsites whose reviews actually changed — not every
        # successfully-synced location. An unconditional daily bust of the full set
        # was the dominant ISR-write source (published microsites x 30/mo).
        changed_loc_ids = [res["location_id"] for res in results
                           if res.get("status") == "success" and res.get("synced_count")]
        if changed_loc_ids:
            from app.services.revalidation_service import trigger_bulk_microsite_revalidation
            trigger_bulk_microsite_revalidation(changed_loc_ids)

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
    import logging
    import redis
    from app.core.config import settings
    from app.models.organization_sync_state import OrganizationSyncState
    from app.services.billing.entitlement_service import EntitlementService
    from app.services import profile_change_service

    logger = logging.getLogger(__name__)

    db: Session = SessionLocal()
    
    org = db.query(Organization).filter(Organization.id == organization_id).first()
    if org and EntitlementService.is_org_locked(org):
        db.close()
        return {"status": "skipped", "reason": "organization is locked"}
    
    r = _get_redis()
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

        # Per-location quota enforcement. Existing locations keep their billing_status
        # (grandfathered — never flipped active->locked). A NEWLY detected location is
        # admitted as 'active' only while we are under the paid quota; otherwise it is
        # inserted 'pending_payment' (visible, but excluded from all paid processing
        # until a prorated charge unlocks it).
        # Card-required onboarding: the very first sync happens BEFORE any payment, and
        # its whole purpose is to audit every location so we can price the mandate for the
        # real count. So admit ALL discovered locations as 'active' (quota = the number
        # found) instead of capping at the trial default. Detected as an org still in the
        # pre-payment onboarding state with no mandate yet. Legacy flow is unchanged.
        onboarding_first_sync = (
            settings.CARD_REQUIRED_ONBOARDING
            and org is not None
            and org.subscription_status == "trial"
            and org.trial_ends_at is None
            and not org.razorpay_subscription_id
        )
        if onboarding_first_sync:
            quota = len(provider_locations)
        else:
            quota = org.location_quota if (org and org.location_quota is not None) else plan_config.TRIAL_LOCATION_QUOTA
        active_count = sum(1 for loc in existing_locations if loc.billing_status == "active")

        # Fields this org published through us in the last few days — Google reports
        # them as differing from our stored row, and they are not third-party edits.
        # One query for the whole org, not one per location.
        own_edits = profile_change_service.recently_published_fields(db, organization_id)

        synced_count = 0
        locked_count = 0
        sync_jobs = []
        for p_loc in provider_locations:
            # Removed debug print
            
            # Check if location already exists in db via map
            existing_loc = existing_locs_map.get(p_loc.provider_location_id)
            
            if existing_loc:
                # Someone may have edited the live listing outside our app since the
                # last sync (staff, a Google suggested edit, Maps feedback). Diff
                # before we overwrite, so the owner sees it in the activity feed.
                # SAVEPOINT, not a bare try/except: on Postgres a failed statement
                # aborts the whole transaction, so swallowing the Python exception
                # would leave the session unusable and take the entire org's sync
                # down with it. begin_nested() rolls back just the detection.
                try:
                    with db.begin_nested():
                        profile_change_service.detect(db, existing_loc, {
                            "location_name": p_loc.name,
                            "phone": p_loc.phone,
                            "additional_phones": p_loc.additional_phones or [],
                            "website": p_loc.website,
                            "address": p_loc.address,
                            "primary_category": p_loc.category,
                            "additional_categories": p_loc.additional_categories or [],
                            "description": p_loc.description,
                            "business_hours": p_loc.business_hours,
                            "special_hours": p_loc.special_hours,
                            "open_info": p_loc.open_info,
                            "service_area": p_loc.service_area,
                            **({"is_verified": p_loc.is_verified,
                                "is_suspended": p_loc.is_suspended}
                               if p_loc.is_verified is not None else {}),
                        }, skip_fields=own_edits.get(existing_loc.id))
                except Exception:
                    # Change detection is informational — never fail a sync over it.
                    logger.exception("profile change detection failed for location %s", existing_loc.id)

                # Update
                existing_loc.google_account_id = p_loc.google_account_id
                existing_loc.location_name = p_loc.name
                existing_loc.primary_category = p_loc.category
                existing_loc.additional_categories = p_loc.additional_categories or []
                existing_loc.additional_phones = p_loc.additional_phones or []
                existing_loc.special_hours = p_loc.special_hours
                existing_loc.more_hours = p_loc.more_hours
                existing_loc.service_area = p_loc.service_area
                existing_loc.service_items = p_loc.service_items
                existing_loc.labels = p_loc.labels or []
                existing_loc.open_info = p_loc.open_info
                # Don't wipe a known latlng (incl. one captured from a local-rank scan)
                # when Google returns none — only overwrite with a real value.
                if p_loc.latlng is not None:
                    existing_loc.latlng = p_loc.latlng
                existing_loc.store_code = p_loc.store_code
                existing_loc.language_code = p_loc.language_code
                existing_loc.gbp_raw = p_loc.gbp_raw
                existing_loc.address = p_loc.address
                # Keep existing geography if a sync omits it, so we never wipe good data.
                existing_loc.city = p_loc.city or existing_loc.city
                existing_loc.state = p_loc.state or existing_loc.state
                existing_loc.country = p_loc.country or existing_loc.country
                existing_loc.postal_code = p_loc.postal_code or existing_loc.postal_code
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
                billing_status = existing_loc.billing_status
            else:
                # Insert new — admit as 'active' only while under quota.
                if active_count < quota:
                    billing_status = "active"
                    active_count += 1
                else:
                    billing_status = "pending_payment"

                new_loc = Location(
                    organization_id=organization_id,
                    google_account_id=p_loc.google_account_id,
                    google_location_id=p_loc.provider_location_id,
                    location_name=p_loc.name,
                    primary_category=p_loc.category,
                    additional_categories=p_loc.additional_categories or [],
                    additional_phones=p_loc.additional_phones or [],
                    special_hours=p_loc.special_hours,
                    more_hours=p_loc.more_hours,
                    service_area=p_loc.service_area,
                    service_items=p_loc.service_items,
                    labels=p_loc.labels or [],
                    open_info=p_loc.open_info,
                    latlng=p_loc.latlng,
                    store_code=p_loc.store_code,
                    language_code=p_loc.language_code,
                    gbp_raw=p_loc.gbp_raw,
                    address=p_loc.address,
                    city=p_loc.city,
                    state=p_loc.state,
                    country=p_loc.country,
                    postal_code=p_loc.postal_code,
                    phone=p_loc.phone,
                    website=p_loc.website,
                    description=p_loc.description,
                    business_hours=p_loc.business_hours,
                    average_rating=p_loc.average_rating,
                    total_reviews=p_loc.total_reviews,
                    is_verified=p_loc.is_verified,
                    is_suspended=p_loc.is_suspended,
                    is_duplicate=p_loc.is_duplicate,
                    billing_status=billing_status,
                    sync_status="Synced",
                    last_synced_at=datetime.datetime.now(datetime.timezone.utc)
                )
                db.add(new_loc)
                db.flush()
                loc_id = new_loc.id

            # Only active locations receive paid downstream processing (review sync,
            # attribute sync, insights). Locked locations are visible but inert.
            if billing_status == "active":
                sync_jobs.append(loc_id)
                synced_count += 1
            else:
                locked_count += 1

        # Commit once after the loop
        db.commit()

        # Recalculate health scores for all synced (active) locations now that
        # their profile details have been updated (location_sync trigger).
        from app.services.health_score_service import HealthScoreService
        for loc_id in sync_jobs:
            HealthScoreService.recalculate_health_score(db, loc_id, reason="location_sync")
        if sync_jobs:
            db.commit()

        # Trigger review sync in chunks
        import time
        chunk_size = getattr(settings, "REVIEW_SYNC_CHUNK_SIZE", 20)
        for i in range(0, len(sync_jobs), chunk_size):
            chunk = sync_jobs[i:i + chunk_size]
            sync_reviews_chunk_task.delay(chunk, organization_id, run_type, user_id)
            time.sleep(0.1)
            
        # Trigger attribute + gallery-photo sync, chunked like reviews above:
        # one dispatch per ~20 locations instead of two per location. Cuts
        # broker commands and per-task overhead ~40x for large orgs.
        for i in range(0, len(sync_jobs), chunk_size):
            sync_location_extras_chunk_task.delay(sync_jobs[i:i + chunk_size])
            
        # Log successful sync operation
        log_message = f"Synchronized {synced_count} locations successfully."
        if locked_count:
            log_message += f" {locked_count} location(s) pending payment (over quota)."
        sync_log.status = "Success"
        sync_log.error_message = log_message
        
        # Update organization sync state
        sync_state.sync_in_progress = False
        sync_state.sync_started_at = None  # Clear: no sync in flight
        sync_state.last_sync_status = "Success"
        sync_state.last_location_sync_at = datetime.datetime.now(datetime.timezone.utc)
        sync_state.last_sync_error = None
        
        db.commit()
        
        # Onboarding billing bookkeeping on first successful sync (status "trial",
        # trial_ends_at still NULL).
        org = db.query(Organization).filter(Organization.id == organization_id).with_for_update().first()
        if org and org.subscription_status == "trial" and org.trial_ends_at is None:
            if settings.CARD_REQUIRED_ONBOARDING:
                # Card-required flow: DON'T start the trial clock here — it starts when the
                # user adds a payment method (see billing trial activation). Only record the
                # discovered active-location count so the mandate bills for all of them.
                if onboarding_first_sync:
                    org.location_quota = active_count
                    db.commit()
            else:
                # Legacy frictionless flow: first sync starts the 7-day trial.
                org.trial_ends_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=plan_config.TRIAL_DAYS)
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
                User.role.in_(ADMIN_ROLES),
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
        from app.services.billing.entitlement_service import EntitlementService
        EntitlementService.transition_expired_subscriptions(db)
        
        # Fetch all active Owner/Admin users who have a connected OAuth account,
        # ordered so the freshest token comes first within each organization.
        # Deduplicate at the query level or fetch only what we need to avoid massive memory usage
        users_with_google = (
            db.query(User.id, User.organization_id)
            .join(OAuthAccount, OAuthAccount.user_id == User.id)
            .filter(
                User.role.in_(ADMIN_ROLES),
                User.is_active == True,
                User.deleted_at.is_(None),
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
            org = db.query(Organization).filter(Organization.id == org_id).first()
            if org and EntitlementService.is_org_locked(org):
                continue
            sync_locations_task.delay(org_id, admin_id, "Scheduled")
            triggered_count += 1

        return f"Triggered synchronization for {triggered_count} organizations."
    finally:
        db.close()


@shared_task(name="app.tasks.notify_superadmin_signup_task")
def notify_superadmin_signup_task(user_id: int) -> dict:
    """Tell the super-admins a new workspace signed up, so someone can follow up.

    Queued rather than sent inline: this hangs off the Google OAuth callback, and a
    third-party HTTP call there would add latency to every signup and risk failing
    the login itself.
    """
    import logging
    from html import escape
    from app.core.config import settings
    from app.services.email_service import send_email

    logger = logging.getLogger(__name__)
    recipients = sorted(settings.superadmin_email_set)
    if not recipients:
        return {"status": "skipped", "reason": "SUPERADMIN_EMAILS not configured"}

    db: Session = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return {"status": "skipped", "reason": "user not found"}
        org = db.query(Organization).filter(Organization.id == user.organization_id).first()

        admin_url = f"{settings.FRONTEND_URL.rstrip('/')}/admin/{user.organization_id}"
        name, email = escape(user.name or "—"), escape(user.email or "—")
        org_name = escape(org.name if org else "—")
        signed_up = user.created_at.strftime("%d %b %Y, %H:%M UTC") if user.created_at else "—"

        html = f"""<div style="font-family:system-ui,-apple-system,sans-serif;max-width:520px">
  <h2 style="margin:0 0 4px">New signup — follow up</h2>
  <p style="color:#666;margin:0 0 20px">Someone just connected Google and created a workspace.</p>
  <table style="width:100%;border-collapse:collapse;font-size:14px">
    <tr><td style="padding:6px 0;color:#888">Name</td><td style="padding:6px 0"><b>{name}</b></td></tr>
    <tr><td style="padding:6px 0;color:#888">Email</td><td style="padding:6px 0"><a href="mailto:{email}">{email}</a></td></tr>
    <tr><td style="padding:6px 0;color:#888">Workspace</td><td style="padding:6px 0">{org_name}</td></tr>
    <tr><td style="padding:6px 0;color:#888">Signed up</td><td style="padding:6px 0">{signed_up}</td></tr>
  </table>
  <p style="margin:24px 0 8px"><b>Reach out while they're still in the product.</b></p>
  <a href="{admin_url}" style="display:inline-block;background:#111;color:#fff;text-decoration:none;padding:12px 24px;border-radius:8px;font-weight:700">Open in admin →</a>
</div>"""

        # Display name is user-controlled and unbounded; keep the subject sane.
        label = " ".join((user.name or user.email or "").split())[:60] or "new user"
        sent = send_email(recipients, f"New signup: {label} — follow up", html)
        logger.info("signup notification for user=%s sent=%s", user_id, sent)
        return {"status": "success" if sent else "failed", "recipients": len(recipients)}
    finally:
        db.close()


@shared_task(name="app.tasks.check_google_updates_task")
def check_google_updates_task(organization_id: int) -> dict:
    """Ask Google whether it has overridden any of this org's live listings.

    Deliberately NOT part of the daily location sync: this costs one extra API call
    per location, and Google's own edits are rare and never urgent. Weekly, over
    active locations of feature-eligible orgs only, is ~10x cheaper than riding the
    sync and loses nothing that matters.
    """
    import logging
    from app.core.config import settings
    from app.services import profile_change_service
    from app.services.billing.entitlement_service import EntitlementService

    logger = logging.getLogger(__name__)
    db: Session = SessionLocal()
    try:
        org = db.query(Organization).filter(Organization.id == organization_id).first()
        if not org or EntitlementService.is_org_locked(org):
            return {"status": "skipped", "reason": "organization is locked"}
        if not plan_config.plan_has_feature(org.plan_tier, plan_config.FEATURE_GOOGLE_UPDATES):
            return {"status": "skipped", "reason": "google_updates not in plan"}
        if not settings.GBP_GOOGLE_UPDATES_ENABLED:
            return {"status": "skipped", "reason": "disabled"}

        # Only locations we actually bill for, and only verified ones — Google has no
        # "updated version" to report for a listing that isn't live.
        locations = db.query(Location).filter(
            Location.organization_id == organization_id,
            Location.billing_status == "active",
            Location.is_verified == True,  # noqa: E712 — SQL comparison, not a bool test
        ).all()
        if not locations:
            return {"status": "success", "checked": 0, "changes": 0}

        provider = ProviderFactory.get_provider("gbp", organization_id, db)
        updated = run_async(provider.get_google_updated([l.google_location_id for l in locations]))

        change_count = 0
        for location in locations:
            blob = updated.get(location.google_location_id)
            if not blob:
                continue
            change_count += len(profile_change_service.detect_google_updates(db, location, blob))
        db.commit()

        logger.info(
            "check_google_updates: org=%s checked=%s diverging=%s new_changes=%s",
            organization_id, len(locations), len(updated), change_count,
        )
        return {"status": "success", "checked": len(locations), "changes": change_count}
    except Exception as e:
        db.rollback()
        logger.error("check_google_updates failed for org %s: %s", organization_id, e, exc_info=True)
        return {"status": "failed", "error": str(e)}
    finally:
        db.close()


@shared_task(name="app.tasks.check_all_google_updates_task")
def check_all_google_updates_task() -> str:
    """Weekly beat entry: fan out check_google_updates_task per eligible org."""
    db: Session = SessionLocal()
    try:
        # Eligibility is decided by plan_has_feature, the same helper the endpoint
        # and the per-org task use. Filtering with SQL `plan_tier IN (...)` instead
        # would silently drop orgs whose plan_tier is NULL — plan_has_feature treats
        # those as the default tier, so they'd pass every other gate and still never
        # be checked.
        rows = db.query(Organization.id, Organization.plan_tier).all()
        org_ids = [
            oid for oid, tier in rows
            if plan_config.plan_has_feature(tier, plan_config.FEATURE_GOOGLE_UPDATES)
        ]
        # Stagger: GBP quota is per-project, so firing every org at once collides
        # with whatever syncs and publishes are already running.
        for i, org_id in enumerate(org_ids):
            check_google_updates_task.apply_async(args=[org_id], countdown=i * 30)
        return f"Queued Google-update checks for {len(org_ids)} organizations."
    finally:
        db.close()


@shared_task(name="app.tasks.transition_subscriptions_task")
def transition_subscriptions_task() -> str:
    """
    Lightweight, DB-only subscription lifecycle sweep
    (trial -> past_due -> locked, and cancelled-active -> locked).

    Decoupled from the heavy location sync so that sync can run on a longer
    interval (cost reduction) WITHOUT delaying expiry/grace transitions. Makes
    no external API calls; idempotent and Redis-lock guarded inside
    EntitlementService, so running it on its own cadence is safe. The same call
    remains inside sync_all_organizations_task as a harmless belt-and-suspenders.
    """
    from app.services.billing.entitlement_service import EntitlementService

    db: Session = SessionLocal()
    try:
        EntitlementService.transition_expired_subscriptions(db)
        return "Subscription lifecycle sweep completed."
    finally:
        db.close()


@shared_task(name="app.tasks.reconcile_pending_subscriptions_task")
def reconcile_pending_subscriptions_task() -> str:
    """Safety net for missed/delayed `subscription.charged` webhooks.

    Finds orgs that have a Razorpay subscription id but are not yet marked active,
    and pulls their real status from Razorpay. If Razorpay says the subscription is
    active/authenticated, entitlements are granted. Idempotent — re-running is safe.
    """
    import logging
    from app.services.billing.subscription_service import SubscriptionService

    logger = logging.getLogger(__name__)
    r = _get_redis()
    # 30-min lease: this loops over all pending orgs making a synchronous Razorpay call
    # each, which can exceed a 5-min TTL and let the lock expire mid-run → concurrent runs.
    lock = r.lock("lock:reconcile_pending_subscriptions", timeout=1800)
    if not lock.acquire(blocking=False):
        return "skipped: another reconcile in progress"

    db: Session = SessionLocal()
    reconciled = 0
    try:
        pending = db.query(Organization).filter(
            Organization.razorpay_subscription_id.isnot(None),
            Organization.subscription_status.notin_(["active", "locked"]),
        ).all()

        for org in pending:
            try:
                if SubscriptionService.reconcile_subscription(db, org.id):
                    reconciled += 1
            except Exception as e:
                db.rollback()
                logger.error(f"Reconcile failed for org {org.id}: {str(e)}")

        # Also retry plan-amount upgrades that failed transiently at add-on time:
        # active orgs whose entitled quota outgrew what the mandate bills, with no
        # re-mandate pending. Left unretried, these bill the old (lower) amount forever.
        drifted = db.query(Organization.id).filter(
            Organization.subscription_status == "active",
            Organization.razorpay_subscription_id.isnot(None),
            Organization.subscription_needs_remandate.is_(False),
            Organization.paid_location_quota.isnot(None),
            Organization.paid_location_quota < Organization.location_quota,
        ).all()
        repaired = 0
        for (org_id,) in drifted:
            try:
                if SubscriptionService.reconcile_plan_amount(db, org_id) in ("upgraded", "needs_remandate"):
                    repaired += 1
            except Exception as e:
                db.rollback()
                logger.error(f"Plan-amount reconcile failed for org {org_id}: {str(e)}")

        return (f"Reconciled {reconciled} subscription(s) of {len(pending)} pending; "
                f"repaired {repaired} of {len(drifted)} drifted plan amount(s).")
    finally:
        db.close()
        try:
            lock.release()
        except Exception:
            pass


@shared_task(name="app.tasks.enforce_upi_remandate_grace_task")
def enforce_upi_remandate_grace_task() -> str:
    """Enforce the UPI re-mandate grace deadline.

    When a location add-on raises a UPI org's quota, Razorpay won't raise the mandate
    amount, so the org is flagged `subscription_needs_remandate` with a deadline of the
    renewal date + 3 days. If the user never approves the new (higher) mandate by then,
    claw the entitled quota back down to what the current mandate actually pays for
    (`paid_location_quota`) and re-lock the surplus locations to 'pending_payment'.

    Idempotent: clears the flag once enforced, and a successful re-mandate (handled at
    cutover) clears the flag first, so re-authorized orgs are never swept.
    """
    import logging
    from datetime import datetime, timezone
    from app.services.billing.pricing_service import PricingService

    logger = logging.getLogger(__name__)
    r = _get_redis()
    lock = r.lock("lock:enforce_upi_remandate_grace", timeout=1800)
    if not lock.acquire(blocking=False):
        return "skipped: another sweep in progress"

    db: Session = SessionLocal()
    locked_orgs = 0
    locked_locs = 0
    try:
        now = datetime.now(timezone.utc)
        candidate_ids = [row[0] for row in db.query(Organization.id).filter(
            Organization.subscription_needs_remandate.is_(True),
            Organization.remandate_due_at.isnot(None),
            Organization.remandate_due_at < now,
        ).all()]

        for org_id in candidate_ids:
            try:
                # Lock the org row and RE-CHECK under the lock: a concurrent re-mandate
                # cutover or renewal webhook (which takes the same row lock) may have
                # cleared the flag or moved the deadline since we listed candidates.
                org = db.query(Organization).filter(
                    Organization.id == org_id
                ).with_for_update().first()
                if not org or not org.subscription_needs_remandate:
                    db.rollback()
                    continue
                if not org.remandate_due_at or org.remandate_due_at >= datetime.now(timezone.utc):
                    db.rollback()
                    continue
                paid = org.paid_location_quota
                if paid is None:
                    paid = org.location_quota or 0
                active_locs = db.query(Location).filter(
                    Location.organization_id == org.id,
                    Location.billing_status == "active",
                ).order_by(Location.id.asc()).all()
                # Keep the oldest `paid` active locations; re-lock the surplus.
                for loc in active_locs[paid:]:
                    loc.billing_status = "pending_payment"
                    locked_locs += 1
                org.location_quota = paid
                org.monthly_ai_credits_balance = PricingService.get_credits_for_locations(
                    paid, org.plan_tier or "basic", org.custom_credits_per_location)
                # Resolved either way: entitled quota now matches the mandate.
                org.subscription_needs_remandate = False
                org.remandate_due_at = None
                # Cancel the abandoned re-mandate so it can't later charge and trigger a
                # surprise cutover after we've already clawed the quota back.
                abandoned = org.pending_remandate_subscription_id
                org.pending_remandate_subscription_id = None
                if abandoned:
                    try:
                        from app.services.billing.subscription_service import SubscriptionService
                        SubscriptionService.get_razorpay_client().subscription.cancel(
                            abandoned, {"cancel_at_cycle_end": 0}
                        )
                    except Exception as e:
                        logger.warning("Failed to cancel abandoned re-mandate sub %s for org %s: %s",
                                       abandoned, org.id, e)
                db.commit()
                locked_orgs += 1
            except Exception as e:
                db.rollback()
                logger.error(f"UPI grace enforcement failed for org {org.id}: {e}")

        return f"Re-locked {locked_locs} location(s) across {locked_orgs} org(s) past grace."
    finally:
        db.close()
        try:
            lock.release()
        except Exception:
            pass


@shared_task(name="app.tasks.purge_soft_deleted_accounts_task")
def purge_soft_deleted_accounts_task() -> str:
    """Hard-purge accounts soft-deleted longer than the grace window.

    A super-admin delete only stamps deleted_at (recoverable via restore). This runs
    daily and, once deleted_at is older than ACCOUNT_PURGE_GRACE_DAYS, permanently
    removes the row. Orgs are deleted via the ORM so cascade rules fan out to all
    children (users, locations, reviews, billing, ...); standalone deleted users are
    removed after (user FKs are SET NULL / CASCADE, so history survives with refs nulled).
    """
    import logging
    from datetime import datetime, timezone, timedelta
    from app.core import plan_config

    logger = logging.getLogger(__name__)
    r = _get_redis()
    lock = r.lock("lock:purge_soft_deleted_accounts", timeout=1800)
    if not lock.acquire(blocking=False):
        return "skipped: another purge in progress"

    db: Session = SessionLocal()
    purged_orgs = purged_users = 0
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=plan_config.ACCOUNT_PURGE_GRACE_DAYS)

        org_ids = [row[0] for row in db.query(Organization.id).filter(
            Organization.deleted_at.isnot(None),
            Organization.deleted_at < cutoff,
        ).all()]
        def _past_grace(deleted_at):
            if deleted_at is None:
                return False
            if deleted_at.tzinfo is None:  # some drivers return naive datetimes
                deleted_at = deleted_at.replace(tzinfo=timezone.utc)
            return deleted_at < cutoff

        for org_id in org_ids:
            try:
                org = db.query(Organization).filter(Organization.id == org_id).first()
                if not org or not _past_grace(org.deleted_at):
                    db.rollback()
                    continue
                # Backstop: normally delete_organization already cancelled the mandate at
                # soft-delete time. Re-cancel here for orgs deleted before that existed, or
                # deleted directly in the DB — once the subscription_id is gone with the row
                # we can never stop the charge. Cancelling an already-cancelled sub is a
                # harmless no-op (logged, not raised).
                from app.services.billing.subscription_service import SubscriptionService
                SubscriptionService.cancel_active_subscriptions(org)
                db.delete(org)   # cascades to all children
                db.commit()
                purged_orgs += 1
                logger.warning("PURGED organization %s (soft-deleted %s) and all its data.",
                               org_id, org.deleted_at)
            except Exception as e:
                db.rollback()
                logger.error("Failed to purge organization %s: %s", org_id, e, exc_info=True)

        # Standalone soft-deleted users (their org still exists; users in a purged org
        # were already removed by the cascade above).
        user_ids = [row[0] for row in db.query(User.id).filter(
            User.deleted_at.isnot(None),
            User.deleted_at < cutoff,
        ).all()]
        for user_id in user_ids:
            try:
                user = db.query(User).filter(User.id == user_id).first()
                if not user or not _past_grace(user.deleted_at):
                    db.rollback()
                    continue
                db.delete(user)
                db.commit()
                purged_users += 1
                logger.warning("PURGED user %s (soft-deleted %s).", user_id, user.deleted_at)
            except Exception as e:
                db.rollback()
                logger.error("Failed to purge user %s: %s", user_id, e, exc_info=True)

        return f"Purged {purged_orgs} organization(s) and {purged_users} user(s) past grace."
    finally:
        db.close()
        try:
            lock.release()
        except Exception:
            pass


@shared_task(name="app.tasks.refill_annual_monthly_credits_task")
def refill_annual_monthly_credits_task() -> str:
    """Refill the monthly AI credit allowance for ANNUAL subscribers.

    Credits otherwise reset only on `subscription.charged`, which fires monthly for
    monthly plans but only once a year for annual plans — so annual orgs would get a
    single month's grant for the whole year. This runs once per calendar month (fixed
    day) so each active annual org gets exactly 12 grants/year. The reset is a SET to
    the full grant (matching apply_subscription_charged), so unused credits don't roll
    over and re-running is idempotent. Monthly plans are untouched — their charge webhook
    already refills them.
    """
    import logging
    from app.services.billing.pricing_service import PricingService

    logger = logging.getLogger(__name__)
    r = _get_redis()
    lock = r.lock("lock:refill_annual_monthly_credits", timeout=1800)
    if not lock.acquire(blocking=False):
        return "skipped: another refill in progress"

    db: Session = SessionLocal()
    refilled = 0
    try:
        annual_orgs = db.query(Organization.id).filter(
            Organization.subscription_status == "active",
            Organization.billing_cycle == "annual",
            Organization.location_quota.isnot(None),
        ).all()
        for (org_id,) in annual_orgs:
            try:
                org = db.query(Organization).filter(
                    Organization.id == org_id
                ).with_for_update().first()
                # Re-check under the lock: a renewal/cancel may have changed state.
                if not org or org.subscription_status != "active" or org.billing_cycle != "annual":
                    db.rollback()
                    continue
                org.monthly_ai_credits_balance = PricingService.get_credits_for_locations(
                    org.location_quota or 0, org.plan_tier or "basic", org.custom_credits_per_location
                )
                db.commit()
                refilled += 1
            except Exception as e:
                db.rollback()
                logger.error(f"Annual credit refill failed for org {org_id}: {e}")
        return f"Refilled monthly credits for {refilled} annual org(s)."
    finally:
        db.close()
        try:
            lock.release()
        except Exception:
            pass


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

    r = _get_redis()
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
        from app.services.sentiment_service import MAX_SENTIMENT_ATTEMPTS
        untagged_reviews = db.query(Review).filter(
            Review.location_id == location_id,
            Review.organization_id == organization_id,
            Review.sentiment_tagged_at == None,  # noqa: E711
            Review.is_deleted == False,
            Review.sentiment_attempts < MAX_SENTIMENT_ATTEMPTS,
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

@shared_task(bind=True, name="app.tasks.auto_reply_reviews_task", max_retries=2)
def auto_reply_reviews_task(self, location_id: int, organization_id: int,
                            backlog: bool = False) -> dict:
    """
    Auto-reply to newly-synced positive reviews from reply templates (or, in AI mode,
    from the LLM). backlog=True instead drips older reviews — see
    drip_ai_backlog_replies_beat_task.
    Thin entry point: owns the Redis lock; orchestration lives in
    ReviewAutoReplyService so it stays unit-testable.
    """
    from app.services.review_auto_reply_service import ReviewAutoReplyService

    r = _get_redis()
    # 30 min, not 5. An AI-mode batch is up to 20 reviews, each an LLM call (30s
    # timeout, 3 attempts) plus a Google POST — a slow run can outlive a 300s lock,
    # and once it expires the next tick starts a second run that re-replies to the
    # same reviews and pays for the generation twice.
    lock = r.lock(f"lock:auto_reply:{organization_id}:{location_id}", timeout=1800)
    if not lock.acquire(blocking=False):
        return {"status": "skipped", "reason": "already running"}

    db: Session = SessionLocal()
    try:
        # Defense-in-depth: auto-reply is a paid capability (not on Lite). The enable
        # endpoint is already gated, but skip here too so a lingering flag can't fire it.
        from app.core import plan_config
        org = db.query(Organization).filter(Organization.id == organization_id).first()
        if not org or not plan_config.plan_has_feature(org.plan_tier, plan_config.FEATURE_AUTO_REPLY):
            return {"status": "skipped", "reason": "auto_reply not in plan"}
        return run_async(ReviewAutoReplyService(db).run(organization_id, location_id, backlog=backlog))
    finally:
        try:
            lock.release()
        except Exception:
            pass
        db.close()


@shared_task(bind=True, name="app.tasks.drip_ai_backlog_replies_beat_task", max_retries=1)
def drip_ai_backlog_replies_beat_task(self) -> dict:
    """Hourly: hand each AI-mode location its next slice of backlog replies.

    Fresh reviews are answered by the sync-triggered task; this only paces the older
    ones, so a 10-20/day quota lands spread over the day instead of in one burst. The
    child task computes what is due from the clock, so a missed tick self-corrects.
    """
    from app.core import plan_config
    from app.services.billing.entitlement_service import EntitlementService
    from app.services.review_auto_reply_service import ReviewAutoReplyService

    db: Session = SessionLocal()
    try:
        rows = (
            db.query(Organization, Location)
            .join(Location, Location.organization_id == Organization.id)
            .filter(
                Organization.auto_reply_mode == "ai",
                Organization.auto_reply_enabled_at.isnot(None),
                Location.billing_status == "active",
                Location.auto_reply_enabled == True,  # noqa: E712
            )
            .all()
        )
        svc = ReviewAutoReplyService(db)
        enqueued = 0
        for org, location in rows:
            if EntitlementService.is_org_locked(org):
                continue
            if not plan_config.plan_has_feature(org.plan_tier, plan_config.FEATURE_AUTO_REPLY):
                continue
            # Two indexed reads here beat a Celery round-trip that would only
            # return "nothing due": steady state is an empty backlog, so without
            # this every AI-mode location costs 24 pointless tasks (and their
            # broker traffic) a day. The child re-checks both — the jitter delay
            # means the numbers can move before it runs.
            if not svc.has_backlog(location) or svc._backlog_room(location) <= 0:
                continue
            location_id = location.id
            # Jitter across the hour so replies don't all land on :00. The child
            # recomputes what is due from the clock, so a later start just means a
            # slightly later post, never a skipped or doubled one.
            auto_reply_reviews_task.apply_async(
                kwargs={"location_id": location_id, "organization_id": org.id, "backlog": True},
                countdown=random.randint(0, 3300),  # 0-55 min
            )
            enqueued += 1
        return {"status": "success", "enqueued": enqueued}
    finally:
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
    
    r = _get_redis()
    lock_key = f"lock:publish_job:{organization_id}:{job_id}"
    # 10-minute lease: must comfortably exceed worst-case create_post (OAuth refresh +
    # GBP create under throttling) so the lock can't expire mid-publish and let a
    # redelivery re-create the post. Stays well under task_time_limit (1800s) and the
    # broker visibility_timeout (3600s).
    lock = r.lock(lock_key, timeout=600)

    if not lock.acquire(blocking=False):
        return {"status": "skipped", "reason": "Job is currently being processed by another worker"}

    db: Session = SessionLocal()
    try:
        logger.info(f"Processing PublishJob {job_id} for Organization {organization_id}")
        job = db.query(PublishJob).filter(PublishJob.id == job_id, PublishJob.organization_id == organization_id).first()
        job_status = job.status.capitalize() if job and job.status else ""
        if not job or job_status not in ["Pending", "Retrying"]:
            return {"status": "skipped", "reason": "Job not found or not in a processable state"}

        if job.campaign_id:
            campaign_status = (r.get(f"campaign:{job.campaign_id}:status") or b"").decode("utf-8")
            if campaign_status in ["Paused", "Cancelled"]:
                job.status = PublishJobStatus.PAUSED.value if campaign_status == "Paused" else PublishJobStatus.CANCELLED.value
                db.commit()
                return {"status": "skipped", "reason": f"Campaign is {campaign_status}"}

        # Idempotency guard against Google: if a prior attempt already created the post
        # (its id is persisted) we must NEVER call create_post again, even on a retry
        # whose previous run failed *after* the Google write but before committing
        # success. GBP exposes no idempotency key, so this persisted-id check is the
        # backstop against duplicate posts.
        if job.google_post_id:
            logger.warning(
                f"PublishJob {job_id} already has google_post_id {job.google_post_id}; "
                f"finalizing as published without re-creating."
            )
            if job.status != PublishJobStatus.SUCCESS.value:
                job.status = PublishJobStatus.SUCCESS.value
                if not job.published_at:
                    job.published_at = datetime.datetime.now(timezone.utc)
                db.commit()
            return {"status": "completed", "google_post_id": job.google_post_id, "idempotent": True}

        # State transition to RUNNING
        job.status = PublishJobStatus.RUNNING.value
        db.commit()

        # Fetch parent post and location details. Eager-load media so the
        # GBP mapper's post.media access doesn't trigger a lazy N+1 per job.
        from sqlalchemy.orm import joinedload
        post = db.query(Post).options(joinedload(Post.media)).filter(Post.id == job.post_id).first()
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
            from sqlalchemy import func
            db.query(Campaign).filter(Campaign.id == job.campaign_id).update({
                Campaign.total_published: Campaign.total_published + 1,
                Campaign.total_pending: func.greatest(0, Campaign.total_pending - 1)
            }, synchronize_session=False)
            
            campaign = db.query(Campaign).filter(Campaign.id == job.campaign_id).first()
            _finalize_campaign_if_complete(db, campaign, organization_id)
        
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
        
        # Recalculate health score
        from app.services.health_score_service import HealthScoreService
        HealthScoreService.recalculate_health_score(db, location.id, reason="post_publish")
        db.commit()

        return {"status": "completed", "google_post_id": job.google_post_id}
    except Exception as e:
        logger.error(f"PublishJob {job_id} failed: {str(e)}")
        db.rollback()
        
        # Decide if error is retryable or not
        is_retryable = _is_retryable_publish_error(e)
            
        # Capture scalar values from the detached ORM objects BEFORE opening a new session,
        # since accessing lazy-loaded attrs on detached objects raises DetachedInstanceError.
        _job_post_id = getattr(job, '__dict__', {}).get('post_id') if job else None

        # Re-fetch job/post inside a fresh session to record the failure safely
        job_db = SessionLocal()
        try:
            job_record = job_db.query(PublishJob).filter(PublishJob.id == job_id).first()
            post_record = job_db.query(Post).filter(Post.id == _job_post_id).first() if _job_post_id else None
            
            if job_record:
                # Capture status details from the exception safely
                err_data = _provider_error_data(e)
                
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
                        from sqlalchemy import func
                        job_db.query(Campaign).filter(Campaign.id == job_record.campaign_id).update({
                            Campaign.total_failed: Campaign.total_failed + 1,
                            Campaign.total_pending: func.greatest(0, Campaign.total_pending - 1)
                        }, synchronize_session=False)
                        
                        campaign = job_db.query(Campaign).filter(Campaign.id == job_record.campaign_id).first()
                        _finalize_campaign_if_complete(job_db, campaign, organization_id)
                    
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
                
                if current_retry < 12: # ~5.5 min total wall clock with backoff below
                    # Backoff 10s -> 20s -> 40s -> 60s cap: media usually optimizes in
                    # the first minute (fast retries preserved), but a slow job no longer
                    # re-runs this whole task every 10s — 12 executions max instead of 30.
                    countdown = min(60, 10 * (2 ** min(current_retry, 3)))
                    logger.info(f"Campaign {campaign_id}: Media is still optimizing. Retrying orchestrator task in {countdown} seconds. (Retry {current_retry + 1}/12)")
                    db.commit()
                    db.close()
                    raise self.retry(countdown=countdown, max_retries=12)
                else:
                    campaign.status = CampaignStatus.FAILED.value
                    db.add(CampaignAuditLog(
                        organization_id=organization_id,
                        campaign_id=campaign.id,
                        actor_user_id=user_id,
                        action="failed",
                        previous_status=CampaignStatus.PROCESSING.value,
                        new_status=CampaignStatus.FAILED.value,
                        log_metadata={"error": "Media optimization timed out (exceeded 10 minutes)."}
                    ))
                    db.commit()
                    return {"status": "error", "reason": "Media optimization timed out."}
        # Delete non-terminal variants/jobs to allow relaunch without unique constraint failures.
        # Preserve SUCCESS/Published records so we don't re-publish already-published locations.
        terminal_statuses = ["Success", "Published", "SUCCESS", "PUBLISHED"]
        succeeded_location_ids = [
            row[0] for row in db.query(PublishJob.location_id).filter(
                PublishJob.post_id == post.id,
                PublishJob.location_id.in_(location_ids),
                PublishJob.status.in_(terminal_statuses)
            ).all()
        ]
        non_succeeded_ids = [lid for lid in location_ids if lid not in succeeded_location_ids]
        if non_succeeded_ids:
            db.query(PostVariant).filter(
                PostVariant.post_id == post.id,
                PostVariant.location_id.in_(non_succeeded_ids)
            ).delete(synchronize_session=False)
            db.query(PublishJob).filter(
                PublishJob.post_id == post.id,
                PublishJob.location_id.in_(non_succeeded_ids),
                PublishJob.status.notin_(terminal_statuses)
            ).delete(synchronize_session=False)
        db.flush()

        # Only process locations that weren't already successfully published
        locations_to_process = non_succeeded_ids if non_succeeded_ids else location_ids
        locations = db.query(Location).filter(Location.id.in_(locations_to_process)).all()
        loc_map = {l.id: l for l in locations}

        for loc_id in locations_to_process:
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
        
        r = _get_redis()
        _ttl = 86400 * 7
        r.set(f"campaign:{campaign_id}:pending_shards", len(shards), ex=_ttl)
        r.set(f"campaign:{campaign_id}:success", 0, ex=_ttl)
        r.set(f"campaign:{campaign_id}:failed", 0, ex=_ttl)
        r.set(f"campaign:{campaign_id}:total_locations", len(job_ids), ex=_ttl)
        r.set(f"campaign:{campaign_id}:status", "Processing", ex=_ttl)
        
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
    r = _get_redis()
    
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

    # Single session for the entire shard — savepoints isolate per-job failures.
    # This avoids opening/closing N connections (one per job) and eliminates the
    # second/third "job_db" / "_retry_db" sessions that were opened on failure.
    db = SessionLocal()
    try:
        # Loop over shard jobs sequentially
        cached_status = campaign_status
        for idx, job_id in enumerate(job_ids):
            # 1. Double check Campaign Status periodically (every 5 jobs)
            if idx > 0 and idx % 5 == 0:
                cached_status = (r.get(f"campaign:{campaign_id}:status") or b"").decode("utf-8")

            if cached_status in ["Paused", "Cancelled"]:
                logger.info(f"Campaign {campaign_id} transitioned to {cached_status}. Tripping circuit breaker for remaining jobs in shard.")
                remaining_ids = job_ids[idx:]
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
                break

            # 2. Queue Jitter & Adaptive Pacing
            if idx > 0:
                jitter = random.uniform(0.8, 1.5)
                time.sleep(jitter)

            # 3. Process individual job inside a savepoint so a failure rolls back
            #    only this job's writes while leaving the outer session usable.
            job = None
            post = None
            try:
                with db.begin_nested() as sp:
                    job = db.query(PublishJob).filter(PublishJob.id == job_id, PublishJob.organization_id == organization_id).first()
                    if not job or job.status not in [PublishJobStatus.PENDING.value, PublishJobStatus.RETRYING.value]:
                        shard_paused_cancelled += 1
                        continue

                    if job.google_post_id:
                        if job.status != PublishJobStatus.SUCCESS.value:
                            job.status = PublishJobStatus.SUCCESS.value
                            if not job.published_at:
                                job.published_at = datetime.datetime.now(datetime.timezone.utc)
                        shard_paused_cancelled += 1
                        continue

                    job.status = PublishJobStatus.RUNNING.value
                    # Flush RUNNING status inside the savepoint so the next savepoint
                    # (success write) builds on it.
                    db.flush()

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

                    res = run_async(provider.create_post(location.google_location_id, payload))

                    job.status = PublishJobStatus.SUCCESS.value
                    job.google_post_id = res.id
                    job.provider_response = getattr(res, "provider_metadata", {}) or {}
                    job.published_at = datetime.datetime.now(datetime.timezone.utc)

                    db.add(PostAuditLog(
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
                    ))
                # savepoint committed — flush to DB
                db.commit()
                r.incr(f"campaign:{campaign_id}:success")
                shard_success += 1

            except Exception as e:
                # Savepoint auto-rolled back; outer session is still valid.
                logger.error(f"Job {job_id} in shard failed: {str(e)}")

                is_retryable = _is_retryable_publish_error(e)

                err_data = _provider_error_data(e)

                try:
                    # Re-fetch via the still-valid session (savepoint rolled back, session ok).
                    job_record = db.query(PublishJob).filter(PublishJob.id == job_id).first()
                    post_id_val = job_record.post_id if job_record else None
                    post_record = db.query(Post).filter(Post.id == post_id_val).first() if post_id_val else None

                    if job_record:
                        current_retries = job_record.retry_count
                        if is_retryable and current_retries < 3:
                            job_record.status = PublishJobStatus.RETRYING.value
                            job_record.last_error = str(e)
                            job_record.retry_count = current_retries + 1
                            job_record.provider_response = err_data
                            db.commit()

                            countdown = 60 * (2 ** current_retries)
                            retry_key = f"campaign:{campaign_id}:retry_registered:{job_id}:{current_retries + 1}"
                            if r.set(retry_key, "1", ex=86400, nx=True):
                                r.incr(f"campaign:{campaign_id}:pending_shards")
                                db.query(Campaign).filter(Campaign.id == campaign_id).update(
                                    {Campaign.total_pending: Campaign.total_pending + 1},
                                    synchronize_session=False
                                )
                                db.commit()
                                process_campaign_shard_task.apply_async(
                                    args=([job_id], organization_id, campaign_id),
                                    countdown=countdown
                                )
                        else:
                            job_record.status = PublishJobStatus.FAILED.value
                            job_record.last_error = str(e)
                            job_record.provider_response = err_data

                            if post_record:
                                db.add(PostAuditLog(
                                    organization_id=organization_id,
                                    post_id=post_record.id,
                                    action="PUBLISH_FAILED",
                                    previous_status="PUBLISHING",
                                    new_status=PostStatus.FAILED.value,
                                    log_metadata={
                                        "error": str(e),
                                        "publish_job_id": job_record.id
                                    }
                                ))

                            db.commit()
                            r.incr(f"campaign:{campaign_id}:failed")
                            shard_failed += 1
                except Exception as retry_err:
                    db.rollback()
                    logger.error(f"Failed to record job failure state: {str(retry_err)}")
    finally:
        # Close the per-shard session opened for the job loop before doing the
        # terminal bookkeeping below (which uses its own short-lived sessions).
        try:
            db.close()
        except Exception:
            pass

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

    if remaining_shards <= 0:
        # NX guard: only one shard may execute the terminal transition even if Redis
        # counter races to negative due to concurrent retries re-incrementing shards.
        acquired = r.set(f"campaign:{campaign_id}:terminal_lock", "1", ex=3600, nx=True)
        if not acquired:
            return

        db = SessionLocal()
        try:
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


def _reconcile_orphaned_publish_jobs(db, r, logger, now, idle_minutes: int = 15, limit: int = 200) -> int:
    """Re-dispatch publish jobs stuck in PENDING.

    Covers the dual-write gap: a worker can commit a job as PENDING and then die
    (or be killed by task_time_limit) before the Celery task is dispatched. Such
    a job would never be picked up again — its parent post is already PUBLISHING,
    so check_scheduled_posts_task's SCHEDULED query never re-selects it.

    Only jobs untouched for `idle_minutes` are eligible, so freshly-staged jobs
    awaiting their already-dispatched task are not disturbed. Re-dispatch is safe:
    process_publish_job_task / process_campaign_shard_task both take a per-job
    Redis lock and short-circuit on a persisted google_post_id, so a job can
    never be double-published.
    """
    from app.models.publish_job import PublishJob
    from app.constants.posts import PublishJobStatus
    from app.worker import celery as celery_app

    cutoff = now - datetime.timedelta(minutes=idle_minutes)
    stuck = db.query(PublishJob).filter(
        PublishJob.status == PublishJobStatus.PENDING.value,
        PublishJob.updated_at < cutoff,
    ).order_by(PublishJob.id.asc()).limit(limit).all()

    redispatched = 0
    for job in stuck:
        try:
            if job.campaign_id:
                celery_app.send_task(
                    "app.tasks.process_campaign_shard_task",
                    args=([job.id], job.organization_id, job.campaign_id),
                )
            else:
                celery_app.send_task(
                    "app.tasks.process_publish_job_task",
                    args=(job.id, job.organization_id),
                )
            redispatched += 1
        except Exception as e:
            logger.error(f"Failed to re-dispatch orphaned PublishJob {job.id}: {e}")

    if redispatched:
        logger.warning(f"Reconciliation re-dispatched {redispatched} orphaned PENDING publish job(s).")
    return redispatched


def _fail_scheduled_post(db, post, reason: str, logger) -> None:
    """Mark a due scheduled post (and its campaign, if any) FAILED + audited, then commit.

    Keeps the post and campaign status in lock-step on the failure path, mirroring
    the success path which moves the campaign to PROCESSING. Without this, a failed
    scheduled campaign post would leave the campaign stuck displaying 'Scheduled'.
    """
    from app.models.campaign import Campaign
    from app.models.campaign_audit_log import CampaignAuditLog
    from app.models.post_audit_log import PostAuditLog
    from app.constants.posts import PostStatus, CampaignStatus

    prev_status = post.status
    post.status = PostStatus.FAILED.value
    db.add(PostAuditLog(
        organization_id=post.organization_id,
        post_id=post.id,
        actor_user_id=post.created_by_user_id,
        action="STATUS_CHANGED",
        previous_status=prev_status,
        new_status=PostStatus.FAILED.value,
        log_metadata={"action": "scheduled_publish_failed", "reason": reason},
    ))

    if post.campaign_id:
        campaign = db.query(Campaign).filter(Campaign.id == post.campaign_id).first()
        if campaign and campaign.status != CampaignStatus.FAILED.value:
            camp_prev = campaign.status
            campaign.status = CampaignStatus.FAILED.value
            db.add(CampaignAuditLog(
                organization_id=post.organization_id,
                campaign_id=campaign.id,
                actor_user_id=post.created_by_user_id,
                action="failed",
                previous_status=camp_prev,
                new_status=CampaignStatus.FAILED.value,
                log_metadata={"error": f"scheduled_publish_failed: {reason}"},
            ))

    db.commit()
    logger.warning(f"Scheduled post {post.id} failed: {reason}.")


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
    from app.models.location import Location
    from app.models.organization import Organization
    from app.models.publish_job import PublishJob
    from app.models.post_audit_log import PostAuditLog
    from app.constants.posts import PostStatus, CampaignStatus, PublishJobStatus
    from app.services.post_service import post_service
    from app.services.activity_log_service import ActivityLogService
    from app.services.billing.entitlement_service import EntitlementService
    import redis
    from app.core.config import settings

    logger = logging.getLogger(__name__)
    db = SessionLocal()
    r = _get_redis()

    # Single-flight guard: a beat run that overruns the 60s interval must not
    # overlap with the next tick. Per-row skip_locked already prevents
    # double-publish, but this avoids redundant scans and reconcile churn.
    # Lease must comfortably exceed the worst-case run so the lock can't expire
    # mid-tick and let the next beat overlap. Kept >= task_time_limit (1800s).
    sched_lock = r.lock("lock:check_scheduled_posts", timeout=1800)
    if not sched_lock.acquire(blocking=False):
        db.close()
        return {"status": "skipped", "reason": "another scheduler run in progress"}

    # How long a scheduled post may wait for its media to finish optimizing
    # before we give up and fail it (mirrors orchestrate_campaign_task's 5-min
    # in-task wait, but measured from the scheduled time since beat is stateless).
    MEDIA_WAIT_MINUTES = getattr(settings, "SCHEDULED_MEDIA_WAIT_MINUTES", 15)

    # Max posts processed per tick. Bounds wall-clock so a large backlog can't
    # overrun the beat interval; the remainder is drained on subsequent ticks
    # (oldest-due first, so nothing starves).
    BATCH_LIMIT = getattr(settings, "SCHEDULED_BATCH_LIMIT", 100)

    now = datetime.datetime.now(datetime.timezone.utc)

    # ── Safety net for the dual-write gap ────────────────────────────────────
    # If a worker died after committing post→PUBLISHING + jobs→PENDING but
    # before dispatching the Celery tasks, those jobs would sit PENDING forever
    # (the post is no longer SCHEDULED, so the query below never re-picks it).
    # Re-dispatch any long-idle PENDING jobs; the publish tasks are idempotent
    # (Redis lock + persisted google_post_id check), so re-dispatch is safe.
    try:
        _reconcile_orphaned_publish_jobs(db, r, logger, now)
    except Exception as recon_err:
        logger.error(f"Orphaned-job reconciliation failed: {recon_err}")
        db.rollback()

    due_post_ids = [p.id for p in db.query(Post.id).filter(
        Post.status == PostStatus.SCHEDULED.value,
        Post.scheduled_at <= now
    ).order_by(Post.scheduled_at.asc()).limit(BATCH_LIMIT).all()]

    processed_count = 0

    try:
        for post_id in due_post_ids:
            try:
                post = db.query(Post).filter(Post.id == post_id).with_for_update(skip_locked=True).first()
                if not post or post.status != PostStatus.SCHEDULED.value:
                    db.rollback()
                    continue

                logger.info(f"Processing scheduled post {post.id} (due at {post.scheduled_at})")

                # ── Entitlement gate ─────────────────────────────────────────
                # Scheduled publishing is a paid feature. If the org locked
                # (subscription lapsed, trial expired) between scheduling and
                # firing, leave the post SCHEDULED so it fires automatically
                # once the org reactivates — never silently publish for a
                # non-entitled org.
                org = db.query(Organization).filter(
                    Organization.id == post.organization_id
                ).first()
                if org and EntitlementService.is_org_locked(org):
                    db.rollback()
                    logger.info(
                        f"Scheduled post {post_id} skipped: organization "
                        f"{post.organization_id} is locked; left as SCHEDULED."
                    )
                    continue

                # ── Media-readiness gate ─────────────────────────────────────
                # The campaign/single-publish workers do NOT wait for media
                # optimization, so we must gate here or risk publishing a post
                # with broken/unoptimized media.
                attached_media = [m for m in post.media if not m.is_deleted]
                invalid_media = [
                    m for m in attached_media
                    if m.validation_status == "Invalid" or m.upload_status == "Failed"
                ]
                if invalid_media:
                    # Permanently broken media — fail the post (don't retry forever).
                    _fail_scheduled_post(db, post, "invalid_or_failed_media", logger)
                    continue

                unready_media = [
                    m for m in attached_media
                    if not m.optimized_url
                    or m.validation_status == "Pending"
                    or m.upload_status == "Pending"
                ]
                if unready_media:
                    # Still optimizing. Leave SCHEDULED so the next beat retries —
                    # unless we've waited past the deadline, then fail.
                    deadline = (
                        post.scheduled_at + datetime.timedelta(minutes=MEDIA_WAIT_MINUTES)
                        if post.scheduled_at else None
                    )
                    if deadline and now > deadline:
                        _fail_scheduled_post(db, post, "media_optimization_timeout", logger)
                    else:
                        db.rollback()
                        logger.info(
                            f"Scheduled post {post_id} waiting on media optimization; "
                            f"left as SCHEDULED."
                        )
                    continue

                target_location_ids = post.target_location_ids or []

                # ── Per-location entitlement gate ────────────────────────────
                # Drop any location that locked (billing_status != active) since
                # scheduling. Mirrors assert_locations_active on the API paths.
                active_location_ids = set()
                if target_location_ids:
                    active_location_ids = {
                        row[0] for row in db.query(Location.id).filter(
                            Location.id.in_(target_location_ids),
                            Location.organization_id == post.organization_id,
                            Location.billing_status == "active",
                        ).all()
                    }
                locked_out = [lid for lid in target_location_ids if lid not in active_location_ids]
                if locked_out:
                    logger.info(
                        f"Scheduled post {post_id}: skipping locked location(s) {locked_out}."
                    )

                old_status = post.status
                post.status = PostStatus.APPROVED.value

                audit_log = PostAuditLog(
                    organization_id=post.organization_id,
                    post_id=post.id,
                    actor_user_id=post.created_by_user_id,
                    action="STATUS_CHANGED",
                    previous_status=old_status,
                    new_status=PostStatus.APPROVED.value,
                    log_metadata={"action": "scheduled_publish_triggered"}
                )
                db.add(audit_log)
                db.flush()

                valid_locations = []
                for loc_id in target_location_ids:
                    if loc_id not in active_location_ids:
                        continue
                    try:
                        post_service._validate_publish_eligibility(
                            db=db,
                            post=post,
                            location_id=loc_id,
                            organization_id=post.organization_id
                        )
                        valid_locations.append(loc_id)
                    except Exception as e:
                        logger.warning(f"Location {loc_id} failed publish eligibility check: {e}")

                if not valid_locations:
                    # No valid locations — revert so the post isn't permanently orphaned as APPROVED.
                    # (If locations were locked, it stays SCHEDULED and fires once they unlock.)
                    post.status = PostStatus.SCHEDULED.value
                    db.commit()
                    logger.warning(f"Scheduled post {post_id} has no valid locations; left as SCHEDULED.")
                    continue

                staged_jobs = []
                for loc_id in valid_locations:
                    job = post_service._stage_publish_job(
                        db=db,
                        post=post,
                        location_id=loc_id,
                        organization_id=post.organization_id,
                        user_id=post.created_by_user_id or 0,
                    )
                    staged_jobs.append(job)

                db.flush()

                if post.campaign_id:
                    campaign = db.query(Campaign).filter(Campaign.id == post.campaign_id).first()
                    if campaign:
                        campaign.total_locations = len(target_location_ids)
                        campaign.total_pending = len(valid_locations)
                        campaign.total_published = 0
                        campaign.total_failed = 0
                        campaign.total_rejected = 0
                        campaign.total_shadow_banned = 0
                        campaign.status = CampaignStatus.PROCESSING.value
                        db.add(campaign)

                ActivityLogService.log(
                    db,
                    organization_id=post.organization_id,
                    entity_type="post",
                    action="publish",
                    actor_user_id=post.created_by_user_id,
                    entity_id=post.id,
                    payload={
                        "mode": "scheduled",
                        "locations_count": len(valid_locations)
                    }
                )

                db.commit()

                from app.worker import celery as celery_app
                campaign_job_ids = [j.id for j in staged_jobs if j.id]

                if post.campaign_id and campaign_job_ids:
                    # Batch into shards of 50 (matches orchestrate_campaign_task behaviour).
                    _chunk_size = 50
                    _shards = [campaign_job_ids[i:i + _chunk_size] for i in range(0, len(campaign_job_ids), _chunk_size)]
                    _ttl = 86400 * 7
                    # pending_shards must equal the number of shards dispatched, not the
                    # number of jobs — _decr_and_flush_terminal_state decrements once per shard.
                    r.set(f"campaign:{post.campaign_id}:pending_shards", len(_shards), ex=_ttl)
                    r.set(f"campaign:{post.campaign_id}:success", 0, ex=_ttl)
                    r.set(f"campaign:{post.campaign_id}:failed", 0, ex=_ttl)
                    r.set(f"campaign:{post.campaign_id}:total_locations", len(valid_locations), ex=_ttl)
                    r.set(f"campaign:{post.campaign_id}:status", "Processing", ex=_ttl)

                    dispatch_errors = []
                    for shard in _shards:
                        try:
                            celery_app.send_task(
                                "app.tasks.process_campaign_shard_task",
                                args=(shard, post.organization_id, post.campaign_id)
                            )
                        except Exception as dispatch_err:
                            dispatch_errors.append((shard, dispatch_err))

                    if dispatch_errors:
                        logger.error(
                            f"Post {post_id}: {len(dispatch_errors)} shard dispatch(es) failed; "
                            f"re-enqueueing with 30s delay. Errors: {dispatch_errors}"
                        )
                        for failed_shard, _ in dispatch_errors:
                            try:
                                celery_app.send_task(
                                    "app.tasks.process_campaign_shard_task",
                                    args=(failed_shard, post.organization_id, post.campaign_id),
                                    countdown=30,
                                )
                            except Exception:
                                logger.exception(f"Re-enqueue also failed for shard {failed_shard}")
                else:
                    # Non-campaign posts: one task per job (single location).
                    dispatch_errors = []
                    for job in staged_jobs:
                        if job.id:
                            try:
                                celery_app.send_task(
                                    "app.tasks.process_publish_job_task",
                                    args=(job.id, post.organization_id)
                                )
                            except Exception as dispatch_err:
                                dispatch_errors.append((job.id, dispatch_err))

                    if dispatch_errors:
                        logger.error(
                            f"Post {post_id}: {len(dispatch_errors)} dispatch(es) failed; "
                            f"re-enqueueing with 30s delay."
                        )
                        for job_id_failed, _ in dispatch_errors:
                            try:
                                celery_app.send_task(
                                    "app.tasks.process_publish_job_task",
                                    args=(job_id_failed, post.organization_id),
                                    countdown=30,
                                )
                            except Exception:
                                logger.exception(f"Re-enqueue also failed for job {job_id_failed}")

                processed_count += 1
            except Exception as post_err:
                logger.error(f"Failed to process scheduled post {post_id}: {str(post_err)}")
                db.rollback()
    finally:
        db.close()
        try:
            sched_lock.release()
        except Exception:
            pass

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
    
    r = _get_redis()
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
        
        gbp_payload = PayloadTransformer.to_gbp_payload(edit.field_name, edit.new_value, location)
        update_mask = FIELD_MAP[edit.field_name].gbp_field_mask
        
        provider = ProviderFactory.get_provider("gbp", organization_id, db)
        
        try:
            res = run_async(provider.patch_location(location.google_location_id, gbp_payload, update_mask))
            ListingEditService.mark_published(db, edit_id=edit.id, organization_id=organization_id)
            db.commit()
            # A published field edit (e.g. the business description) changes profile
            # completeness, so refresh the health score for an accurate before/after.
            try:
                from app.services.health_score_service import HealthScoreService
                HealthScoreService.recalculate_health_score(db, location.id, reason="listing_edit_publish")
                db.commit()
            except Exception as hs_err:
                logger.warning("Health score recalc failed after listing-edit publish %s: %s", edit.id, hs_err)
                
            from app.services.revalidation_service import trigger_bulk_microsite_revalidation
            trigger_bulk_microsite_revalidation([location.id])
            
            return {"status": "completed"}
            
        except Exception as e:
            logger.error(f"PublishListingEdit {edit_id} failed: {str(e)}")
            is_retryable = _is_retryable_publish_error(e)
            google_error_code = None
            if isinstance(e, PermanentAuthError):
                google_error_code = "AUTH_REVOKED"
            elif isinstance(e, httpx.HTTPStatusError):
                google_error_code = str(e.response.status_code)
                
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

@shared_task(bind=True, name="app.tasks.publish_location_media_task", max_retries=3)
def publish_location_media_task(self, media_id: int, organization_id: int) -> dict:
    """Publish a LocationMedia row's asset to the location's GBP photo gallery."""
    import logging
    import httpx
    from app.db.session import SessionLocal
    from app.models.location_media import LocationMedia, LocationMediaStatus
    from app.models.location import Location
    from app.providers.factory import ProviderFactory
    from app.providers.gbp.auth import PermanentAuthError
    from app.services.health_score_service import HealthScoreService

    logger = logging.getLogger(__name__)

    r = _get_redis()
    lock = r.lock(f"lock:publish_location_media:{media_id}", timeout=120)
    if not lock.acquire(blocking=False):
        return {"status": "skipped", "reason": "Already being published by another worker"}

    db = SessionLocal()
    try:
        media = db.query(LocationMedia).filter(
            LocationMedia.id == media_id,
            LocationMedia.organization_id == organization_id,
        ).first()
        if not media:
            return {"status": "skipped", "reason": "LocationMedia not found"}
        if media.publish_status == LocationMediaStatus.PUBLISHED or media.published_at is not None:
            return {"status": "skipped", "reason": "Idempotency guard: already published"}
        if media.publish_status != LocationMediaStatus.PUBLISHING:
            return {"status": "skipped", "reason": f"Not in Publishing state: {media.publish_status}"}

        location = db.query(Location).filter(Location.id == media.location_id).first()
        if not location:
            raise Exception("Location not found.")

        media.publish_attempts += 1
        db.commit()

        provider = ProviderFactory.get_provider("gbp", organization_id, db)
        try:
            item = run_async(provider.create_location_media(
                location.google_location_id,
                media.source_url,
                media.gbp_category,
            ))
            media.gbp_resource_name = item.resource_name
            media.media_key = item.media_key
            if item.media_format:
                media.media_format = item.media_format
            if item.thumbnail_url:
                media.thumbnail_url = item.thumbnail_url
            media.publish_status = LocationMediaStatus.PUBLISHED
            media.published_at = datetime.datetime.now(timezone.utc)
            media.failure_reason = None
            media.google_error_code = None
            db.commit()

            # Confirm-by-list: re-fetch the gallery and reconcile against Google's
            # authoritative record. Catches an accept-then-reject and refreshes the
            # category / hosted URL / thumbnail Google actually assigned. Best-effort
            # — propagation lag means "not yet listed" is not treated as a failure.
            try:
                gallery = run_async(provider.list_location_media(location.google_location_id))
                match = next((g for g in gallery if g.media_key and g.media_key == media.media_key), None)
                if match:
                    media.gbp_category = match.category or media.gbp_category
                    media.media_format = match.media_format or media.media_format
                    if match.source_url:
                        media.source_url = match.source_url
                    if match.thumbnail_url:
                        media.thumbnail_url = match.thumbnail_url
                    db.commit()
            except Exception as confirm_err:
                logger.warning(f"Confirm-by-list skipped for media {media_id}: {confirm_err}")

            try:
                HealthScoreService.recalculate_health_score(db, media.location_id, reason="location_media_publish")
                db.commit()
            except Exception as hs_err:
                logger.warning(f"Health score recalc failed after media publish {media_id}: {hs_err}")

            return {"status": "completed"}

        except Exception as e:
            logger.error(f"PublishLocationMedia {media_id} failed: {str(e)}")
            is_retryable = _is_retryable_publish_error(e)
            google_error_code = None
            if isinstance(e, PermanentAuthError):
                google_error_code = "AUTH_REVOKED"
            elif isinstance(e, httpx.HTTPStatusError):
                google_error_code = str(e.response.status_code)

            if is_retryable and self.request.retries < self.max_retries:
                countdown = 60 * (2 ** self.request.retries)
                db.close()
                raise self.retry(exc=e, countdown=countdown)

            media.publish_status = LocationMediaStatus.FAILED
            media.failure_reason = str(e)
            media.google_error_code = google_error_code
            db.commit()
            return {"status": "failed", "reason": str(e)}
    finally:
        try:
            lock.release()
        except Exception:
            pass
        db.close()


@shared_task(bind=True, name="app.tasks.delete_location_media_task", max_retries=3)
def delete_location_media_task(self, media_id: int, organization_id: int) -> dict:
    """Delete a gallery photo from Google, then soft-delete the local record."""
    import logging
    import httpx
    from app.db.session import SessionLocal
    from app.models.location_media import LocationMedia
    from app.models.location import Location
    from app.providers.factory import ProviderFactory
    from app.providers.gbp.auth import PermanentAuthError
    from app.services.health_score_service import HealthScoreService

    logger = logging.getLogger(__name__)
    db = SessionLocal()
    try:
        media = db.query(LocationMedia).filter(
            LocationMedia.id == media_id,
            LocationMedia.organization_id == organization_id,
        ).first()
        if not media or media.is_deleted:
            return {"status": "skipped", "reason": "Not found or already deleted"}

        location = db.query(Location).filter(Location.id == media.location_id).first()
        if not location:
            return {"status": "skipped", "reason": "Location not found"}

        media_key = media.media_key
        if media_key:
            provider = ProviderFactory.get_provider("gbp", organization_id, db)
            try:
                run_async(provider.delete_location_media(location.google_location_id, media_key))
            except Exception as e:
                logger.error(f"DeleteLocationMedia {media_id} failed: {str(e)}")
                is_retryable = isinstance(e, (httpx.RequestError, TimeoutError, ConnectionError))
                if is_retryable and self.request.retries < self.max_retries:
                    countdown = 60 * (2 ** self.request.retries)
                    db.close()
                    raise self.retry(exc=e, countdown=countdown)
                # Non-retryable (e.g. already gone on Google) — fall through to local delete.

        media.is_deleted = True
        media.deleted_at = datetime.datetime.now(timezone.utc)
        db.commit()

        try:
            HealthScoreService.recalculate_health_score(db, media.location_id, reason="location_media_delete")
            db.commit()
        except Exception as hs_err:
            logger.warning(f"Health score recalc failed after media delete {media_id}: {hs_err}")

        return {"status": "deleted"}
    finally:
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
def sync_insights_task(location_id: int, start_date_str: str, end_date_str: str, run_type: str = "Scheduled", scope: str = "all") -> dict:
    """
    Celery task to synchronize daily performance insights for a location.
    Enforces Redis locking to prevent concurrent synchronizations.

    `scope` controls which data is synced:
      - "daily":    only daily performance metrics (Performance Insights page)
      - "keywords": only monthly search keywords (Search Intelligence page)
      - "all":      both (nightly beat / full refresh)
    """
    if scope not in ("daily", "keywords", "all"):
        scope = "all"
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

        # Sync Window Protection
        if run_type != "Manual":
            today = datetime.date.today()
            first_day_this_month = today.replace(day=1)
            last_day_prev_month = first_day_this_month - datetime.timedelta(days=1)
            first_day_prev_month = last_day_prev_month.replace(day=1)
            
            if start_date < first_day_prev_month:
                start_date = first_day_prev_month
                logger.info(f"Background sync window restricted. Adjusted start_date to {start_date}")

        r = _get_redis()
        lock_key = f"lock:sync_insights:{organization_id}:{location_id}"
        lock = r.lock(lock_key, timeout=300)

        if not lock.acquire(blocking=False):
            logger.warning(f"Skipping insights sync for location {location_id}: lock already held")
            return {"status": "skipped", "reason": "insights sync already in progress"}

        try:
            res_msg = None
            res_kw_msg = None

            # Daily performance metrics.
            if scope in ("daily", "all"):
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

            # Search keywords. Keyword insights are monthly, so we use a dedicated
            # (wider) window than the daily-insights sync: a manual/force refresh
            # backfills a full year so the 6/12-month range selector has data;
            # scheduled runs stay light (current + previous month).
            if scope in ("keywords", "all"):
                from app.services.keyword_sync_service import KeywordSyncService
                kw_end = datetime.date.today()
                kw_months_back = 12 if run_type == "Manual" else 1
                _m = kw_end.month - 1 - kw_months_back
                kw_start = datetime.date(kw_end.year + _m // 12, _m % 12 + 1, 1)
                logger.info(f"Executing KeywordSyncService for location {location_id} ({kw_start}..{kw_end})...")
                res_kw_msg = run_async(KeywordSyncService.sync_location_keywords(
                    db=db,
                    location_id=location_id,
                    start_date=kw_start,
                    end_date=kw_end,
                    run_type=run_type
                ))
                logger.info(f"Keyword sync completed for location {location_id}: {res_kw_msg}")

            return {"status": "success", "scope": scope, "message": res_msg, "keyword_message": res_kw_msg}
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

@shared_task(name="app.tasks.sync_organization_insights_task")
def sync_organization_insights_task(organization_id: int, start_date_str: str, end_date_str: str, run_type: str = "Scheduled", force: bool = False, scope: str = "all") -> dict:
    """
    Celery task to orchestrate insights synchronization for an entire organization.
    Uses organization-level Redis lock and OrganizationSyncState.

    `scope` ("daily" | "keywords" | "all") is forwarded to each per-location
    sync so the Performance Insights and Search Intelligence pages can refresh
    independently.
    """
    if scope not in ("daily", "keywords", "all"):
        scope = "all"
    import redis
    import datetime
    import logging
    from app.core.config import settings
    from app.models.organization_sync_state import OrganizationSyncState
    from app.models.location import Location

    logger = logging.getLogger(__name__)
    logger.info(f"Starting sync_organization_insights_task for org={organization_id}, force={force}")

    db: Session = SessionLocal()
    r = _get_redis()
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

            # Query all active locations (ids only — the loop just enqueues tasks)
            locations = db.query(Location.id).filter(
                Location.organization_id == organization_id,
                Location.sync_status != "Failed",
                Location.billing_status == "active"  # locked locations get no paid processing
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
                        run_type=run_type,
                        scope=scope
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
    from app.services.billing.entitlement_service import EntitlementService
    db: Session = SessionLocal()
    try:
        orgs = db.query(Organization).all()
        today = datetime.date.today()
        yesterday = today - datetime.timedelta(days=1)
        start_date = today - datetime.timedelta(days=7)

        enqueued_count = 0
        for org in orgs:
            # Locked/expired orgs get no paid processing — same guard as
            # sync_all_organizations_task. Skipping here saves the child task's
            # Redis lock + sync-state writes per locked org every night.
            if EntitlementService.is_org_locked(org):
                continue
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
        from app.services.sentiment_service import MAX_SENTIMENT_ATTEMPTS
        from app.services.billing.entitlement_service import EntitlementService
        from app.models.organization import Organization

        # Find locations with untagged reviews that haven't exhausted their attempts
        untagged_locations = db.query(Review.location_id, Review.organization_id).filter(
            Review.sentiment_tagged_at == None,
            Review.is_deleted == False,
            Review.sentiment_attempts < MAX_SENTIMENT_ATTEMPTS,
        ).distinct().all()

        # Locked/expired orgs get no paid LLM work (same gate the sync beats use).
        org_ids = {org_id for _, org_id in untagged_locations}
        unlocked_org_ids = set()
        if org_ids:
            for org in db.query(Organization).filter(Organization.id.in_(org_ids)).all():
                if not EntitlementService.is_org_locked(org):
                    unlocked_org_ids.add(org.id)

        enqueued = 0
        for loc_id, org_id in untagged_locations:
            if org_id not in unlocked_org_ids:
                continue
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

@shared_task(name="app.tasks.sync_location_extras_chunk_task")
def sync_location_extras_chunk_task(location_ids: list) -> dict:
    """Attribute + gallery sync for a batch of locations.

    Runs the two single-location tasks in-process for each id. The single-id
    tasks stay as-is because the API/webhook layers still dispatch them
    individually by name (billing.py, location_media.py, webhook_service.py).
    """
    import logging
    logger = logging.getLogger(__name__)
    changed_loc_ids = []
    for loc_id in location_ids:
        try:
            sync_location_attributes_task(loc_id)
        except Exception as e:
            logger.error(f"attribute sync failed for location {loc_id}: {e}")
        try:
            res = sync_location_media_task(loc_id, revalidate=False)
            if res.get("inserted") or res.get("updated") or res.get("removed"):
                changed_loc_ids.append(loc_id)
        except Exception as e:
            logger.error(f"media sync failed for location {loc_id}: {e}")
    # One revalidation for the whole chunk (mirrors the review-sync path).
    if changed_loc_ids:
        from app.services.revalidation_service import trigger_bulk_microsite_revalidation
        trigger_bulk_microsite_revalidation(changed_loc_ids)
    return {"status": "success", "count": len(location_ids)}


@shared_task(name="app.tasks.sync_location_media_task")
def sync_location_media_task(location_id: int, revalidate: bool = True) -> dict:
    """Reconcile the location's real Google photo gallery into location_media.

    Pulls every media item Google reports (including photos uploaded outside our
    app) and upserts by media_key: inserts pre-existing photos as Published with
    no local source file, refreshes view counts, and soft-deletes rows whose
    photo was removed on Google's side. Leaves in-flight (Pending/Publishing)
    rows untouched.
    """
    import logging
    from app.db.session import SessionLocal
    from app.models.location_media import LocationMedia, LocationMediaStatus
    from app.models.location import Location
    from app.providers.factory import ProviderFactory
    from app.services.health_score_service import HealthScoreService

    logger = logging.getLogger(__name__)
    db = SessionLocal()
    try:
        location = db.query(Location).filter(Location.id == location_id).first()
        if not location or not location.google_location_id:
            return {"status": "skipped", "reason": "Location not found / no google id"}
        if location.is_verified is False:
            return {"status": "skipped", "reason": "Location not verified"}

        provider = ProviderFactory.get_provider("gbp", location.organization_id, db)
        try:
            items = run_async(provider.list_location_media(location.google_location_id))
        except Exception as e:
            logger.warning(f"sync_location_media_task list failed for {location_id}: {e}")
            return {"status": "error", "reason": str(e)}

        google_keys = {it.media_key for it in items if it.media_key}

        # Existing rows already known to Google (have a media_key), not in-flight.
        existing = db.query(LocationMedia).filter(
            LocationMedia.location_id == location_id,
            LocationMedia.organization_id == location.organization_id,
            LocationMedia.media_key.isnot(None),
            LocationMedia.is_deleted == False,
        ).all()
        existing_by_key = {m.media_key: m for m in existing}

        now = datetime.datetime.now(timezone.utc)
        inserted = updated = removed = 0

        for it in items:
            if not it.media_key:
                continue
            row = existing_by_key.get(it.media_key)
            if row:
                row.gbp_resource_name = it.resource_name or row.gbp_resource_name
                if it.source_url:
                    row.source_url = it.source_url
                if it.thumbnail_url:
                    row.thumbnail_url = it.thumbnail_url
                if it.media_format:
                    row.media_format = it.media_format
                if it.category:
                    row.gbp_category = it.category
                row.publish_status = LocationMediaStatus.PUBLISHED
                updated += 1
            else:
                db.add(LocationMedia(
                    organization_id=location.organization_id,
                    location_id=location_id,
                    source_media_id=None,
                    gbp_category=it.category or "ADDITIONAL",
                    media_format=it.media_format or "PHOTO",
                    gbp_resource_name=it.resource_name,
                    media_key=it.media_key,
                    source_url=it.source_url or "",
                    thumbnail_url=it.thumbnail_url,
                    publish_status=LocationMediaStatus.PUBLISHED,
                    published_at=now,
                ))
                inserted += 1

        # Photos removed on Google's side → reflect locally.
        for key, row in existing_by_key.items():
            if key not in google_keys:
                row.is_deleted = True
                row.deleted_at = now
                removed += 1

        db.commit()

        try:
            HealthScoreService.recalculate_health_score(db, location_id, reason="location_media_sync")
            db.commit()
        except Exception as hs_err:
            logger.warning(f"Health score recalc failed after media sync {location_id}: {hs_err}")

        # revalidate=False lets batch callers (extras chunk) revalidate once for the
        # whole chunk instead of once per location — 4k-location syncs were firing
        # 4k revalidations and starving the DB pool. Skip entirely if nothing changed.
        if revalidate and (inserted or updated or removed):
            from app.services.revalidation_service import trigger_bulk_microsite_revalidation
            trigger_bulk_microsite_revalidation([location_id])

        return {"status": "success", "inserted": inserted, "updated": updated, "removed": removed}
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
            User.role.in_(ADMIN_ROLES),
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
        try:
            r = _get_redis()
            r.delete(f"location:attributes_schema:{location_id}")
            logger.info(f"Invalidated form schema cache for location {location_id} in publish task finally block")
        except Exception as cache_err:
            logger.error(f"Failed to invalidate cache in publish task finally block for location {location_id}: {cache_err}")
        db.close()




@shared_task(name="app.tasks.fire_purchase_conversion_task")
def fire_purchase_conversion_task(payment_id: str, amount_paise: int, currency: str,
                                  email: str = None, attribution: dict = None,
                                  user_id: int = None) -> str:
    """Send server-side Purchase conversions (Meta CAPI + Google Ads) out-of-band, so
    the Razorpay webhook never holds the org lock during external HTTP. Best-effort."""
    from app.services.marketing_service import fire_purchase_conversion
    fire_purchase_conversion(
        payment_id=payment_id,
        amount_paise=amount_paise,
        currency=currency,
        email=email,
        attribution=attribution or {},
        user_id=user_id,
    )
    return f"conversion dispatched for payment {payment_id}"


@shared_task(name="app.tasks.run_aeo_scan_task")
def run_aeo_scan_task(scan_id: int) -> dict:
    """Run a queued AI-Visibility (AEO) scan via the real DataForSEO provider.

    No credit charge — AEO is quota-metered (one scan/location/month), and the
    Pending scan row already claims that quota. `aeo_service.run_scan` marks the
    scan Failed on any provider error, which refunds the quota (Failed rows don't
    count). Enqueued only when AEO_PROVIDER != "mock".
    """
    import logging
    from app.models.aeo_scan import AEOScan
    from app.services import aeo_service

    logger = logging.getLogger(__name__)
    db: Session = SessionLocal()
    try:
        scan = db.query(AEOScan).filter(AEOScan.id == scan_id).first()
        if not scan:
            return {"status": "error", "reason": "scan not found"}
        location = db.query(Location).filter(Location.id == scan.location_id).first()
        if not location:
            scan.status = "Failed"
            scan.error = "Location not found"
            db.commit()
            return {"status": "error", "reason": "location not found"}

        aeo_service.run_scan(db, scan, location)
        money = (scan.result or {}).get("money_spent")
        logger.info("AEO scan %s finished: status=%s money_spent=%s", scan_id, scan.status, money)
        return {"status": scan.status, "money_spent": money}
    except Exception as e:  # noqa: BLE001 — never leave a stuck Pending row
        db.rollback()
        scan = db.query(AEOScan).filter(AEOScan.id == scan_id).first()
        if scan and scan.status == "Pending":
            scan.status = "Failed"
            scan.error = str(e)[:500]
            db.commit()
        raise
    finally:
        db.close()


@shared_task(name="app.tasks.release_lpseo_index_batch_task")
def release_lpseo_index_batch_task() -> dict:
    """Hourly: flip local-SEO pages whose drip-feed moment has arrived.

    No Redis lock and no per-page state. The sweep is a single indexed query filtered
    on index_status='noindex', so a re-run or an overlapping tick simply finds nothing
    left to do. Hourly rather than per-minute keeps beat wakeups (and Upstash
    commands) low; the only cost is up to an hour of lag on a page going live, which
    is meaningless for a schedule measured in weeks.
    """
    import logging
    from app.core.redis_client import get_redis
    from app.db.session import SessionLocal
    from app.services import lpseo_drip
    from app.services.revalidation_service import trigger_bulk_lpseo_revalidation

    logger = logging.getLogger(__name__)
    db = SessionLocal()
    try:
        released = lpseo_drip.release_due(db)
        if released:
            # Bust the BACKEND cache before asking the frontend to revalidate.
            # Without this the flip to index is invisible: the public endpoint keeps
            # serving the cached noindex payload for up to an hour, the frontend
            # revalidates immediately, caches that stale answer for its full TTL, and
            # the drip has already spent its one revalidation. The page then stays
            # noindex on the live site indefinitely.
            # One delete for the whole tick, not one per page (Upstash bills per command).
            try:
                get_redis().delete(*[f"public_lpseo:{r['slug']}" for r in released])
            except Exception:
                logger.warning("lpSEO drip: cache purge failed; revalidating anyway", exc_info=True)
            # Narrow per-page and per-industry tags, so a handful of pages going live
            # never fans out into a corpus-wide ISR rebuild.
            trigger_bulk_lpseo_revalidation(released)
        return {"released": len(released), "slugs": [r["slug"] for r in released]}
    except Exception:
        db.rollback()
        logger.exception("lpSEO drip release failed")
        raise
    finally:
        db.close()
