import os
from sqlalchemy import create_engine, text

DATABASE_URL = "postgresql://postgres:postgres@localhost:5435/gmb_db"
engine = create_engine(DATABASE_URL)

def check_defs():
    with engine.connect() as conn:
        print("--- Definitions Check ---")
        query = text("SELECT category_id, attribute_id, display_name, value_type FROM gbp_attribute_definitions WHERE category_id IN ('gcid:jeweller', 'gcid:jewellery_store')")
        res = conn.execute(query).fetchall()
        for r in res:
            print(r)

if __name__ == "__main__":
    check_defs()
