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
def sync_reviews_task(location_id: int, run_type: str = "Scheduled") -> str:
    """
    Synchronizes reviews for a specific location via the ReviewSyncService.
    """
    db: Session = SessionLocal()
    try:
        # Run the async sync_location_reviews inside a synchronous celery task wrapper
        return asyncio.run(ReviewSyncService.sync_location_reviews(db, location_id, run_type))
    finally:
        db.close()

@shared_task(name="app.tasks.sync_locations_task")
def sync_locations_task(organization_id: int, user_id: int, run_type: str = "Scheduled") -> str:
    """
    Synchronizes Google Business Profile locations for an organization
    using the user's encrypted tokens fetched from the oauth_accounts table.
    Gracefully handles token refreshing and encryption/decryption cycles.
    """
    db: Session = SessionLocal()
    
    try:
        provider = ProviderFactory.get_provider("gbp", organization_id, db)
        provider_locations = asyncio.run(provider.get_locations())
        
        synced_count = 0
        for p_loc in provider_locations:
            print(f"DEBUG: Processing location: {p_loc.name}")
            
            # Check if location already exists in db
            existing_loc = db.query(Location).filter(
                Location.organization_id == organization_id,
                Location.google_location_id == p_loc.provider_location_id
            ).first()
            
            if existing_loc:
                # Update
                existing_loc.location_name = p_loc.name
                existing_loc.primary_category = p_loc.category
                existing_loc.address = p_loc.address
                existing_loc.phone = p_loc.phone
                existing_loc.website = p_loc.website
                existing_loc.average_rating = p_loc.average_rating
                existing_loc.total_reviews = p_loc.total_reviews
                existing_loc.sync_status = "Synced"
                existing_loc.last_synced_at = datetime.datetime.utcnow()
            else:
                # Insert new
                new_loc = Location(
                    organization_id=organization_id,
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
                
            synced_count += 1
            
        db.commit()
        
        # Log successful sync operation
        log_message = f"Synchronized {synced_count} locations successfully."
        sync_log = SyncLog(
            organization_id=organization_id,
            status="Success",
            run_type=run_type,
            error_message=log_message
        )
        db.add(sync_log)
        db.commit()
        
        return f"SUCCESS: {log_message}"

    except Exception as e:
        db.rollback()
        
        # If refreshing has failed catastrophically
        if isinstance(e, ProviderAuthError) or "re-authentication required" in str(e).lower() or "invalid_grant" in str(e).lower():
            # Find and delete oauth account
            oauth_account = db.query(OAuthAccount).join(User).filter(User.organization_id == organization_id).first()
            if oauth_account:
                db.delete(oauth_account)
                db.commit()
            
        # Log failure
        error_msg = f"Sync Failed: {str(e)}"
        sync_log = SyncLog(
            organization_id=organization_id,
            status="Failed",
            run_type=run_type,
            error_message=error_msg
        )
        db.add(sync_log)
        db.commit()
        
        # Flag existing locations as failed
        db.query(Location).filter(Location.organization_id == organization_id).update({
            Location.sync_status: "Failed"
        })
        db.commit()
        
        return f"FAILED: {error_msg}"
        
    finally:
        db.close()

@shared_task(name="app.tasks.sync_all_organizations_task")
def sync_all_organizations_task() -> str:
    """
    Periodic task enqueuing background synchronizations for organizations.
    Iterates over users and locates their active oauth credentials.
    """
    db: Session = SessionLocal()
    try:
        users_with_google = db.query(User).join(OAuthAccount).filter(User.role == "Admin").all()
        triggered_count = 0
        
        for admin in users_with_google:
            sync_locations_task.delay(admin.organization_id, admin.id, "Scheduled")
            triggered_count += 1
                
        return f"Triggered synchronization for {triggered_count} organizations."
    finally:
        db.close()
