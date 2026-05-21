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
from app.core.gbp_client import GBPClient

@shared_task(name="app.tasks.sync_locations_task")
def sync_locations_task(organization_id: int, user_id: int, run_type: str = "Scheduled") -> str:
    """
    Synchronizes Google Business Profile locations for an organization
    using the user's encrypted tokens fetched from the oauth_accounts table.
    Gracefully handles token refreshing and encryption/decryption cycles.
    """
    db: Session = SessionLocal()
    
    # 1. Fetch User
    user = db.query(User).filter(User.id == user_id, User.organization_id == organization_id).first()
    if not user:
        db.close()
        return f"User {user_id} not found."

    # 2. Fetch OAuth Credentials
    oauth_account = db.query(OAuthAccount).filter(OAuthAccount.user_id == user_id).first()
    if not oauth_account:
        # Create log failure
        sync_log = SyncLog(
            organization_id=organization_id,
            status="Failed",
            run_type=run_type,
            error_message="Sync Failed: Google account is disconnected. Please re-authenticate."
        )
        db.add(sync_log)
        db.commit()
        db.close()
        return f"Sync aborted: No Google OAuth Account found for user {user_id}."

    # 3. Expiry check and refresh
    now = datetime.datetime.now(timezone.utc)
    # Ensure token_expiry is aware for comparison
    token_expiry = oauth_account.expires_at
    if token_expiry and token_expiry.tzinfo is None:
        token_expiry = token_expiry.replace(tzinfo=timezone.utc)
    
    # Decrypt credentials
    try:
        access_token = decrypt_token(oauth_account.access_token)
        if not access_token:
            raise Exception("Failed to decrypt access token.")
    except Exception:
        db.close()
        return f"Sync aborted: Could not decrypt access token for user {user_id}."

    try:
        refresh_token = decrypt_token(oauth_account.refresh_token)
    except Exception:
        refresh_token = None

    def perform_refresh():
        if not refresh_token:
            raise Exception("Google credentials expired or invalid. Refresh token missing. Re-authentication required.")
            
        print(f"Refreshing Google access token for user {user.email}...")
        
        # Request fresh access token
        new_token_data = GBPClient.refresh_access_token(refresh_token)
        
        # Save new encrypted token and expiry
        new_access_token = new_token_data["access_token"]
        oauth_account.access_token = encrypt_token(new_access_token)
        
        # Google sometimes rotates refresh tokens
        new_refresh_token = new_token_data.get("refresh_token")
        if new_refresh_token:
            oauth_account.refresh_token = encrypt_token(new_refresh_token)
        
        # Update expiry
        expires_in = new_token_data.get("expires_in", 3600)
        oauth_account.expires_at = datetime.datetime.now(timezone.utc) + datetime.timedelta(seconds=expires_in)
        
        db.commit()
        print("Access token refreshed successfully.")
        return new_access_token

    try:
        # 1. Proactive Refresh: If token has expired or is expiring within 5 minutes
        if not token_expiry or token_expiry <= now + datetime.timedelta(minutes=5):
            access_token = perform_refresh()

        # 4. Instantiate GBP Client and fetch locations
        client = GBPClient(access_token=access_token, refresh_token=refresh_token)
        
        try:
            google_locations = client.fetch_locations()
        except Exception as e:
            # 2. Reactive Refresh: If we get an error that looks like a 401/expired token, try to refresh once
            if "401" in str(e) or "unauthorized" in str(e).lower() or "expired" in str(e).lower():
                print(f"Token rejected by Google (401). Attempting reactive refresh for {user.email}...")
                access_token = perform_refresh()
                # Retry with new token
                client = GBPClient(access_token=access_token, refresh_token=refresh_token)
                google_locations = client.fetch_locations()
            else:
                raise e
        
        # 5. Sync locations into database
        synced_count = 0
        for g_loc in google_locations:
            print(f"DEBUG: Processing location: {g_loc.get('title')}")
            print(f"DEBUG: Full location data: {g_loc}")
            
            g_id = g_loc.get("name") # Format: "locations/123456"
            if not g_id:
                continue
                
            title = g_loc.get("title", "Unnamed Location")
            category = g_loc.get("categories", {}).get("primaryCategory", {}).get("displayName")
            
            addr_info = g_loc.get("storefrontAddress", {})
            lines = addr_info.get("addressLines", [])
            locality = addr_info.get("locality", "")
            region = addr_info.get("administrativeArea", "")
            full_address = ", ".join(lines + [locality, region]).strip(", ")
            
            phone = g_loc.get("phoneNumbers", {}).get("primaryPhone")
            website = g_loc.get("websiteUri")
            rating = g_loc.get("rating")
            reviews = g_loc.get("reviewCount")
            
            # Check if location already exists in db
            existing_loc = db.query(Location).filter(
                Location.organization_id == organization_id,
                Location.google_location_id == g_id
            ).first()
            
            if existing_loc:
                # Update
                existing_loc.location_name = title
                existing_loc.primary_category = category
                existing_loc.address = full_address
                existing_loc.phone = phone
                existing_loc.website = website
                existing_loc.average_rating = rating
                existing_loc.total_reviews = reviews
                existing_loc.sync_status = "Synced"
                existing_loc.last_synced_at = datetime.datetime.utcnow()
            else:
                # Insert new
                new_loc = Location(
                    organization_id=organization_id,
                    google_location_id=g_id,
                    location_name=title,
                    primary_category=category,
                    address=full_address,
                    phone=phone,
                    website=website,
                    average_rating=rating,
                    total_reviews=reviews,
                    sync_status="Synced",
                    last_synced_at=datetime.datetime.utcnow()
                )
                db.add(new_loc)
                
            synced_count += 1
            
        db.commit()
        
        # 6. Log successful sync operation
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
        # If refreshing has failed catastrophically, delete the oauth_account to force re-auth
        if "re-authentication required" in str(e).lower() or "invalid_grant" in str(e).lower():
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
