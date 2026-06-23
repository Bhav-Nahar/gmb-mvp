import sys
import os

# Add backend directory to sys.path so we can import app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal
from app.models.location import Location
from app.services.comparison_cache_service import ComparisonCacheService

def main():
    db = SessionLocal()
    try:
        locations = db.query(Location).filter(Location.gbp_raw.isnot(None)).all()
        updated_count = 0
        touched_orgs = set()

        for loc in locations:
            raw = loc.gbp_raw or {}
            address = raw.get("storefrontAddress") or raw.get("postalAddress") or {}

            # Keep existing value when the raw payload is missing a field, so a
            # malformed gbp_raw can't wipe good geography data.
            city = address.get("locality") or loc.city
            state = address.get("administrativeArea") or loc.state
            country = address.get("regionCode") or loc.country
            postal_code = address.get("postalCode") or loc.postal_code

            if loc.city != city or loc.state != state or loc.country != country or loc.postal_code != postal_code:
                loc.city = city
                loc.state = state
                loc.country = country
                loc.postal_code = postal_code
                updated_count += 1
                touched_orgs.add(loc.organization_id)

        db.commit()
        # City/State comparison groups locations by these fields — clear stale caches.
        for org_id in touched_orgs:
            ComparisonCacheService.invalidate_comparison_cache(org_id)
        print(f"Successfully backfilled geography fields for {updated_count} locations.")
    except Exception as e:
        db.rollback()
        print(f"Error during backfill: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    main()
