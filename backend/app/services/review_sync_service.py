import datetime
import hashlib
import json
import logging
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import func
from app.models.review import Review
from app.models.location import Location
from app.models.sync_log import SyncLog
from app.models.organization_sync_state import OrganizationSyncState
from app.providers.factory import ProviderFactory

logger = logging.getLogger(__name__)

def generate_content_hash(rating: int, comment: str, reply_text: str, updated_at, reply_created_at=None) -> str:
    if updated_at:
        if updated_at.tzinfo is not None:
            updated_at = updated_at.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        updated_at_str = updated_at.isoformat()
    else:
        updated_at_str = ''
        
    if reply_created_at:
        if reply_created_at.tzinfo is not None:
            reply_created_at = reply_created_at.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        reply_created_at_str = reply_created_at.isoformat()
    else:
        reply_created_at_str = ''

    hash_str = f"{rating or 0}:{comment or ''}:{reply_text or ''}:{updated_at_str}:{reply_created_at_str}"
    return hashlib.sha256(hash_str.encode('utf-8')).hexdigest()


def _record_sync_log(db, sync_log, organization_id, location_id, run_type, status, message):
    """Update the passed-in SyncLog row if present, else insert a fresh one, then commit."""
    if sync_log:
        sync_log.status = status
        sync_log.error_message = message
    else:
        db.add(SyncLog(
            organization_id=organization_id,
            location_id=location_id,
            status=status,
            run_type=run_type,
            error_message=message,
        ))
    db.commit()


class ReviewSyncService:
    @staticmethod
    async def sync_location_reviews(db: Session, location_id: int, run_type: str = "Scheduled", sync_log_id: int = None) -> str:
        """
        Sync reviews for a specific local location using State-Aware Delta Sync.
        """
        location = db.query(Location).filter(Location.id == location_id).first()
        if not location:
            raise Exception(f"Location with ID {location_id} not found.")

        organization_id = location.organization_id
        
        sync_log = None
        if sync_log_id:
            sync_log = db.query(SyncLog).filter(SyncLog.id == sync_log_id).first()
        
        try:
            # 1. Fetch Location Sync Metadata
            sync_state = db.query(OrganizationSyncState).filter(OrganizationSyncState.organization_id == organization_id).first()
            loc_metadata = sync_state.location_sync_metadata.get(f"loc_{location_id}", {}) if sync_state and sync_state.location_sync_metadata else {}
            
            latest_update_str = loc_metadata.get("latest_review_update_at")
            safe_cutoff_time = None
            if latest_update_str:
                latest_update = datetime.datetime.fromisoformat(latest_update_str)
                if latest_update.tzinfo is None:
                    latest_update = latest_update.replace(tzinfo=datetime.timezone.utc)
                safe_cutoff_time = latest_update - datetime.timedelta(days=2)
            
            # 2. Fetch reviews from provider with sliding safety window
            provider_name = "gbp"
            provider = ProviderFactory.get_provider(provider_name, organization_id, db)
            try:
                provider_reviews = await provider.get_reviews(location.google_location_id, safe_cutoff_time=safe_cutoff_time)
            except Exception as fetch_err:
                logger.error("Provider fetch failed for location %s: %s", location_id, fetch_err)
                error_msg = f"ProviderError: {str(fetch_err)}"
                _record_sync_log(db, sync_log, organization_id, location_id, run_type, "ProviderError", error_msg)
                return f"PROVIDER_ERROR: {error_msg}"

            if not provider_reviews:
                log_msg = "Successfully synced 0 reviews."
                _record_sync_log(db, sync_log, organization_id, location_id, run_type, "Success", log_msg)
                return f"SUCCESS: {log_msg}"
            
            # 3. Filter out reviews with missing provider IDs
            valid_reviews = [pr for pr in provider_reviews if pr.id]
            if len(valid_reviews) < len(provider_reviews):
                logger.warning("Skipped %d reviews with missing IDs", len(provider_reviews) - len(valid_reviews))
            provider_reviews = valid_reviews

            # 4. Load existing review hashes for delta detection
            provider_ids = [pr.id for pr in provider_reviews]
            existing_reviews = db.query(
                Review.provider_review_id, 
                Review.content_hash,
                Review.rating,
                Review.comment,
                Review.sentiment_tagged_at,
                Review.sentiment,
                Review.issue_category
            ).filter(
                Review.location_id == location_id,
                Review.provider_review_id.in_(provider_ids)
            ).all()
            existing_reviews_map = {r.provider_review_id: r for r in existing_reviews}
            
            # 4. Delta Detection
            reviews_to_upsert = []
            max_update_time = safe_cutoff_time or datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)
            if max_update_time.tzinfo is None:
                max_update_time = max_update_time.replace(tzinfo=datetime.timezone.utc)
            
            for pr in provider_reviews:
                rev_updated_at = pr.updated_at or pr.created_at or datetime.datetime.now(datetime.timezone.utc)
                if rev_updated_at.tzinfo is None:
                    rev_updated_at = rev_updated_at.replace(tzinfo=datetime.timezone.utc)
                if rev_updated_at > max_update_time:
                    max_update_time = rev_updated_at
                    
                new_hash = generate_content_hash(pr.rating, pr.body, pr.reply, pr.updated_at, pr.reply_created_at)
                old_review = existing_reviews_map.get(pr.id)
                old_hash = old_review.content_hash if old_review else None
                
                if new_hash != old_hash:
                    sentiment_reset = True
                    if old_review:
                        if old_review.rating == pr.rating and (old_review.comment or "") == (pr.body or ""):
                            sentiment_reset = False
                    
                    reviews_to_upsert.append((pr, new_hash, sentiment_reset, old_review))
            
            synced_count = len(reviews_to_upsert)
            
            # 5. Conditional UPSERT
            if reviews_to_upsert:
                chunk_size = 500
                for i in range(0, len(reviews_to_upsert), chunk_size):
                    chunk = reviews_to_upsert[i:i + chunk_size]
                    
                    insert_values = []
                    for pr, new_hash, sentiment_reset, old_review in chunk:
                        insert_values.append({
                            "organization_id": organization_id,
                            "location_id": location_id,
                            "provider": pr.provider,
                            "provider_review_id": pr.id,
                            "reviewer_name": pr.reviewer_name,
                            "reviewer_profile_photo": pr.reviewer_profile_photo,
                            "rating": pr.rating,
                            "comment": pr.body,
                            "is_replied": bool(pr.reply),
                            "reply_text": pr.reply,
                            "reply_created_at": pr.reply_created_at,
                            "review_created_at": pr.created_at or datetime.datetime.now(datetime.timezone.utc),
                            "review_updated_at": pr.updated_at,
                            "raw_payload": pr.provider_metadata,
                            "created_at": datetime.datetime.now(datetime.timezone.utc),
                            "updated_at": datetime.datetime.now(datetime.timezone.utc),
                            "is_deleted": False,
                            "content_hash": new_hash,
                            "sentiment_tagged_at": None if sentiment_reset else (old_review.sentiment_tagged_at if old_review else None),
                            "sentiment": None if sentiment_reset else (old_review.sentiment if old_review else None),
                            "issue_category": None if sentiment_reset else (old_review.issue_category if old_review else None)
                        })
                    
                    stmt = insert(Review).values(insert_values)
                    stmt = stmt.on_conflict_do_update(
                        constraint="uq_review_provider_id",
                        set_={
                            "reviewer_name": stmt.excluded.reviewer_name,
                            "reviewer_profile_photo": stmt.excluded.reviewer_profile_photo,
                            "rating": stmt.excluded.rating,
                            "comment": stmt.excluded.comment,
                            "is_replied": stmt.excluded.is_replied,
                            "reply_text": stmt.excluded.reply_text,
                            "reply_created_at": stmt.excluded.reply_created_at,
                            "review_updated_at": stmt.excluded.review_updated_at,
                            "raw_payload": stmt.excluded.raw_payload,
                            "updated_at": func.now(),
                            "is_deleted": False,
                            "content_hash": stmt.excluded.content_hash,
                            "sentiment_tagged_at": stmt.excluded.sentiment_tagged_at,
                            "sentiment": stmt.excluded.sentiment,
                            "issue_category": stmt.excluded.issue_category
                        }
                    )
                    db.execute(stmt)

                # NOTE: commit deferred — combined with location metadata update below

                # 6. Event-Driven AI Enqueueing
                from app.worker import celery as celery_app
                celery_app.send_task(
                    "app.tasks.tag_reviews_sentiment_task",
                    kwargs={
                        "location_id": location_id,
                        "organization_id": organization_id
                    }
                )
            
            # Update location summary stats
            stats = db.query(
                func.count(Review.id).label("count"),
                func.avg(Review.rating).label("avg")
            ).filter(
                Review.location_id == location_id,
                Review.is_deleted == False
            ).one()
            
            location.total_reviews = stats.count
            location.average_rating = float(stats.avg) if stats.avg else 0.0
            
            # Update OrganizationSyncState location metadata
            if sync_state:
                current_meta = json.loads(json.dumps(sync_state.location_sync_metadata)) if sync_state.location_sync_metadata else {}
                loc_key = f"loc_{location_id}"
                loc_data = current_meta.get(loc_key, {})
                loc_data["latest_review_update_at"] = max_update_time.isoformat()
                loc_data["last_review_sync_completed_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
                loc_data["last_review_sync_status"] = "Success"
                current_meta[loc_key] = loc_data
                sync_state.location_sync_metadata = current_meta
            
            from app.services.activity_log_service import ActivityLogService
            try:
                ActivityLogService.log(
                    db,
                    organization_id=organization_id,
                    location_id=location_id,
                    actor_user_id=None,
                    entity_type="system",
                    action="reviews_synced",
                    payload={"synced_count": synced_count, "total_fetched": len(provider_reviews)}
                )
            except Exception as log_err:
                logger.warning("ActivityLogService.log failed (non-fatal): %s", log_err)

            # Single atomic commit: review upserts + location metadata update
            db.commit()

            # Log successful sync
            log_message = f"Successfully synced {synced_count} reviews (from {len(provider_reviews)} fetched)."
            _record_sync_log(db, sync_log, organization_id, location_id, run_type, "Success", log_message)

            return f"SUCCESS: {log_message}"

        except Exception as e:
            db.rollback()
            error_msg = f"Review Sync Failed: {str(e)}"
            _record_sync_log(db, sync_log, organization_id, location_id, run_type, "Failed", error_msg)
            raise e

review_sync_service = ReviewSyncService()
