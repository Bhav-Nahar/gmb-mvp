import os
from sqlalchemy import create_engine, text

DATABASE_URL = "postgresql://postgres:postgres@db:5432/gmb_db"
engine = create_engine(DATABASE_URL)

def check_attribute(attr_id):
    with engine.connect() as conn:
        print(f"--- Checking attribute: {attr_id} ---")
        query = text("SELECT category_id, attribute_id, display_name, value_type, is_repeatable FROM gbp_attribute_definitions WHERE attribute_id = :attr_id")
        res = conn.execute(query, {"attr_id": attr_id}).fetchall()
        if not res:
            print("No definitions found.")
        for r in res:
            print(r)

if __name__ == "__main__":
    check_attribute("attributes/has_onsite_services")
