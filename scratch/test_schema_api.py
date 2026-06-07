import os
import sys

# MUST SET THIS BEFORE IMPORTS
os.environ["DATABASE_URL"] = "postgresql://postgres:postgres@localhost:5435/gmb_db"

# Add backend to sys.path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from app.db.session import SessionLocal
from app.models.location import Location
from app.models.gbp_attribute_definition import GbpAttributeDefinition
from app.api.dynamic_attributes import get_category_id

def test_schema_endpoint():
    db = SessionLocal()
    try:
        # Test for location 98
        loc = db.query(Location).filter(Location.id == 98).first()
        print(f"Location: {loc.location_name}, Category: {loc.primary_category}")
        
        category_id = get_category_id(loc.primary_category)
        print(f"Mapped Category ID: {category_id}")
        
        definitions = db.query(GbpAttributeDefinition).filter(
            GbpAttributeDefinition.category_id == category_id,
            GbpAttributeDefinition.is_active == True
        ).all()
        
        print(f"Definitions found in test: {len(definitions)}")
        for df in definitions:
            print(f"- {df.attribute_id}: {df.display_name}")

    finally:
        db.close()

if __name__ == "__main__":
    test_schema_endpoint()
