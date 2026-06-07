
from app.db.session import SessionLocal
from app.services.attribute_sync_service import AttributeSyncService
import asyncio

async def run():
    db = SessionLocal()
    try:
        service = AttributeSyncService(db)
        print("Re-syncing category metadata for gcid:home_help...")
        await service.sync_category_metadata(organization_id=226, category_id="gcid:business", region_code="IN", language_code="en")
        print("Re-sync complete.")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(run())
