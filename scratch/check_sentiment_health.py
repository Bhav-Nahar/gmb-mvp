import os
from sqlalchemy import create_engine, text

DATABASE_URL = "postgresql://postgres:postgres@localhost:5435/gmb_db"
engine = create_engine(DATABASE_URL)

def check_sync_logs():
    with engine.connect() as conn:
        print("--- Latest 20 Sync Logs ---")
        query = text("SELECT id, status, LEFT(error_message, 100), created_at FROM sync_logs ORDER BY created_at DESC LIMIT 20")
        res = conn.execute(query)
        for row in res:
            print(row)

def check_untagged_reviews():
    with engine.connect() as conn:
        print("\n--- Untagged Reviews Count ---")
        query = text("SELECT COUNT(*) FROM reviews WHERE sentiment_tagged_at IS NULL AND is_deleted = False")
        count = conn.execute(query).scalar()
        print(f"Total untagged reviews: {count}")

if __name__ == "__main__":
    check_sync_logs()
    check_untagged_reviews()
