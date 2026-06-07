import asyncio
import os
import sys

# MUST SET THIS BEFORE IMPORTS
os.environ["DATABASE_URL"] = "postgresql://postgres:postgres@localhost:5435/gmb_db"

# Add backend to sys.path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from app.services.attribute_sync_service import AttributeSyncService
from app.db.session import SessionLocal

async def test_coffee_shop():
    db = SessionLocal()
    try:
        service = AttributeSyncService(db)
        print("Syncing metadata for gcid:coffee_shop...")
        # Use an org_id that has a token, org 210 seemed to work
        await service.sync_category_metadata(210, "gcid:coffee_shop", "US", "en")
        
        from app.models.gbp_attribute_definition import GbpAttributeDefinition
        count = db.query(GbpAttributeDefinition).filter(GbpAttributeDefinition.category_id == "gcid:coffee_shop").count()
        print(f"Coffee Shop definitions found: {count}")
        
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(test_coffee_shop())
