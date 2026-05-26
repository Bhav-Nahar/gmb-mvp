import datetime
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import func
from app.models.review import Review
from app.models.location import Location
from app.models.sync_log import SyncLog
from app.providers.factory import ProviderFactory

class ReviewSyncService:
    @staticmethod
    async def sync_location_reviews(db: Session, location_id: int, run_type: str = "Scheduled", sync_log_id: int = None) -> str:
        """
        Sync reviews for a specific local location.
        """
        location = db.query(Location).filter(Location.id == location_id).first()
        if not location:
            raise Exception(f"Location with ID {location_id} not found.")

        organization_id = location.organization_id
        
        sync_log = None
        if sync_log_id:
            sync_log = db.query(SyncLog).filter(SyncLog.id == sync_log_id).first()
        
        try:
            # We assume Google Business Profile for MVP, but can read provider from location if implemented
            provider_name = "gbp"
            provider = ProviderFactory.get_provider(provider_name, organization_id, db)
            
            # Fetch reviews from provider using the external location ID
            provider_reviews = await provider.get_reviews(location.google_location_id)
            
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
            
            # Batch upsert using ON CONFLICT DO UPDATE
            chunk_size = 500
            synced_count = 0
            
            for i in range(0, len(provider_reviews), chunk_size):
                chunk = provider_reviews[i:i + chunk_size]
                
                insert_values = []
                for pr in chunk:
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
                        "review_created_at": pr.created_at or datetime.datetime.utcnow(),
                        "review_updated_at": pr.updated_at,
                        "raw_payload": pr.provider_metadata,
                        "created_at": datetime.datetime.utcnow(),
                        "updated_at": datetime.datetime.utcnow(),
                        "is_deleted": False
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
                        "review_updated_at": stmt.excluded.review_updated_at,
                        "raw_payload": stmt.excluded.raw_payload,
                        "updated_at": func.now(),
                        "is_deleted": False, # Restore softly deleted reviews if they still exist in provider
                    }
                )
                
                db.execute(stmt)
                synced_count += len(chunk)

            db.commit()

            # Update location summary stats from the newly synced reviews
            # This handles cases where the initial V4 summary fetch in location sync might have failed
            stats = db.query(
                func.count(Review.id).label("count"),
                func.avg(Review.rating).label("avg")
            ).filter(
                Review.location_id == location_id,
                Review.is_deleted == False
            ).one()
            
            location.total_reviews = stats.count
            location.average_rating = float(stats.avg) if stats.avg else 0.0
            db.commit()

            # Log successful sync
            log_message = f"Successfully synced {synced_count} reviews."
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
