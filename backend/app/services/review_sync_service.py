import datetime
import hashlib
import json
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import func
from app.models.review import Review
from app.models.location import Location
from app.models.sync_log import SyncLog
from app.models.organization_sync_state import OrganizationSyncState
from app.providers.factory import ProviderFactory

def generate_content_hash(rating: int, comment: str, reply_text: str, updated_at, reply_created_at) -> str:
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
            provider_reviews = await provider.get_reviews(location.google_location_id, safe_cutoff_time=safe_cutoff_time)
            
            if not provider_reviews:
                log_msg = "Successfully synced 0 reviews."
                if sync_log:
                    sync_log.status = "Success"
                    sync_log.error_message = log_msg
                else:
                    new_log = SyncLog(
                        organization_id=organization_id,
                        location_id=location_id,
                        status="Success",
                        run_type=run_type,
                        error_message=log_msg
                     )
                    db.add(new_log)
                db.commit()
                return f"SUCCESS: {log_msg}"
            
            # 3. Load existing review hashes for delta detection
            provider_ids = [pr.id for pr in provider_reviews]
            existing_reviews = db.query(Review.provider_review_id, Review.content_hash).filter(
                Review.location_id == location_id,
                Review.provider_review_id.in_(provider_ids)
            ).all()
            existing_hashes = {r.provider_review_id: r.content_hash for r in existing_reviews}
            
            # 4. Delta Detection
            reviews_to_upsert = []
            max_update_time = safe_cutoff_time or datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)
            if max_update_time.tzinfo is None:
                max_update_time = max_update_time.replace(tzinfo=datetime.timezone.utc)
            
            for pr in provider_reviews:
                rev_updated_at = pr.updated_at or pr.created_at or datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)
                if rev_updated_at.tzinfo is None:
                    rev_updated_at = rev_updated_at.replace(tzinfo=datetime.timezone.utc)
                if rev_updated_at > max_update_time:
                    max_update_time = rev_updated_at
                    
                new_hash = generate_content_hash(pr.rating, pr.body, pr.reply, pr.updated_at)
                old_hash = existing_hashes.get(pr.id)
                
                if new_hash != old_hash:
                    reviews_to_upsert.append((pr, new_hash))
            
            synced_count = len(reviews_to_upsert)
            
            # 5. Conditional UPSERT
            if reviews_to_upsert:
                chunk_size = 500
                for i in range(0, len(reviews_to_upsert), chunk_size):
                    chunk = reviews_to_upsert[i:i + chunk_size]
                    
                    insert_values = []
                    for pr, new_hash in chunk:
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
                            "review_created_at": pr.created_at or datetime.datetime.utcnow(),
                            "review_updated_at": pr.updated_at,
                            "raw_payload": pr.provider_metadata,
                            "created_at": datetime.datetime.utcnow(),
                            "updated_at": datetime.datetime.utcnow(),
                            "is_deleted": False,
                            "content_hash": new_hash,
                            "sentiment_tagged_at": None # Reset to NULL for AI to process
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
                            "reply_created_at": Review.__table__.c.reply_created_at,
                            "review_updated_at": stmt.excluded.review_updated_at,
                            "raw_payload": stmt.excluded.raw_payload,
                            "updated_at": func.now(),
                            "is_deleted": False,
                            "content_hash": stmt.excluded.content_hash,
                            "sentiment_tagged_at": None # Reset for reprocessing
                        }
                    )
                    db.execute(stmt)

                db.commit()
                
                # 6. Event-Driven AI Enqueueing
                # Fetch IDs of the newly upserted reviews
                upserted_provider_ids = [pr.id for pr, _ in reviews_to_upsert]
                upserted_review_ids = db.query(Review.id).filter(
                    Review.location_id == location_id,
                    Review.provider_review_id.in_(upserted_provider_ids)
                ).all()
                
                from app.worker import celery as celery_app
                for (rid,) in upserted_review_ids:
                    celery_app.send_task("app.tasks.process_review_sentiment_task", args=[rid])
            
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
                loc_data["last_review_sync_completed_at"] = datetime.datetime.utcnow().isoformat()
                loc_data["last_review_sync_status"] = "Success"
                current_meta[loc_key] = loc_data
                sync_state.location_sync_metadata = current_meta
            
            from app.services.activity_log_service import ActivityLogService
            ActivityLogService.log(
                db,
                organization_id=organization_id,
                location_id=location_id,
                actor_user_id=None,
                entity_type="system",
                action="reviews_synced",
                payload={"synced_count": synced_count, "total_fetched": len(provider_reviews)}
            )
            
            db.commit()

            # Log successful sync
            log_message = f"Successfully synced {synced_count} reviews (from {len(provider_reviews)} fetched)."
            if sync_log:
                sync_log.status = "Success"
                sync_log.error_message = log_message
            else:
                new_log = SyncLog(
                    organization_id=organization_id,
                    location_id=location_id,
                    status="Success",
                    run_type=run_type,
                    error_message=log_message
                )
                db.add(new_log)
            db.commit()

            return f"SUCCESS: {log_message}"

        except Exception as e:
            db.rollback()
            error_msg = f"Review Sync Failed: {str(e)}"
            if sync_log:
                sync_log.status = "Failed"
                sync_log.error_message = error_msg
            else:
                new_log = SyncLog(
                    organization_id=organization_id,
                    location_id=location_id,
                    status="Failed",
                    run_type=run_type,
                    error_message=error_msg
                )
                db.add(new_log)
            db.commit()
            raise e

review_sync_service = ReviewSyncService()
