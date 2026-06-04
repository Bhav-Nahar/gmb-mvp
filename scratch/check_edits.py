import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5435/gmb_db")
# If running on host, the port in docker-compose is 5435.
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
session = Session()

try:
    from sqlalchemy import text
    res = session.execute(text("SELECT id, field_name, status, new_value, publish_attempts, failure_reason FROM location_edits ORDER BY id DESC LIMIT 5"))
    print("Latest 5 location edits in database:")
    for row in res:
        print(f"ID: {row[0]}, Field: {row[1]}, Status: {row[2]}, Attempts: {row[4]}, Error: {row[5]}")
except Exception as e:
    print("Error querying database:", e)
finally:
    session.close()
