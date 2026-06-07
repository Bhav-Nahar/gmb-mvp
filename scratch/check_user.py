import os
from sqlalchemy import create_engine, text

DATABASE_URL = "postgresql://postgres:postgres@localhost:5435/gmb_db"
engine = create_engine(DATABASE_URL)

def check_user():
    with engine.connect() as conn:
        print("--- User Check ---")
        query = text("SELECT u.id, u.email, u.organization_id, u.role, o.name FROM users u JOIN organizations o ON u.organization_id = o.id WHERE u.email = 'marketing@lucirajewelry.com'")
        res = conn.execute(query).fetchone()
        print(f"User: {res}")
        
        if res:
            org_id = res[2]
            print(f"\n--- Locations for Org {org_id} ---")
            loc_query = text("SELECT id, location_name FROM locations WHERE organization_id = :org_id")
            locs = conn.execute(loc_query, {"org_id": org_id}).fetchall()
            for l in locs:
                print(l)

if __name__ == "__main__":
    check_user()
