import os
import sys

# MUST SET THIS BEFORE IMPORTS
os.environ["DATABASE_URL"] = "postgresql://postgres:postgres@localhost:5435/gmb_db"

# Add backend to sys.path
sys.path.append(os.path.join(os.getcwd(), "backend"))

import asyncio
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.services.attribute_sync_service import AttributeSyncService
from app.models.location import Location
from app.db.session import SessionLocal

async def fix_missing_attributes():
    db = SessionLocal()
    try:
        # 1. Sync metadata for categories found in DB
        locations = db.query(Location).all()
        service = AttributeSyncService(db)
        
        categories = set((loc.primary_category, loc.organization_id) for loc in locations if loc.primary_category)
        print(f"Syncing metadata for {len(categories)} categories...")
        
        for cat_name, org_id in categories:
            # Map to gcid
            cat_id = cat_name.lower().replace(" ", "_")
            if not cat_id.startswith("gcid:"):
                cat_id = f"gcid:{cat_id}"
            
            print(f"Syncing category: {cat_name} ({cat_id}) for org: {org_id}")
            try:
                await service.sync_category_metadata(org_id, cat_id, "US", "en")
            except Exception as e:
                print(f"Error syncing metadata for {cat_name}: {e}")
        
        # 2. Sync attributes for each location
        print("\nSyncing attributes for all locations...")
        for loc in locations:
            print(f"Syncing attributes for: {loc.location_name} (ID: {loc.id})")
            try:
                await service.fetch_location_attributes(loc.id)
            except Exception as e:
                print(f"Error syncing attributes for {loc.id}: {e}")
        
        print("\nSync complete.")
        
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(fix_missing_attributes())
