import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Common DATABASE_URL fallback for local dev
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5435/gmb_db")

def check_audit_logs():
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # Check general audit logs
        print("--- Latest 10 General Audit Logs ---")
        res = session.execute(text("SELECT id, action, actor_user_id, target_user_id, created_at FROM audit_logs ORDER BY created_at DESC LIMIT 10"))
        for row in res:
            print(f"ID: {row[0]} | Action: {row[1]} | Actor: {row[2]} | Target: {row[3]} | At: {row[4]}")
        
        # Check campaign audit logs
        print("\n--- Latest 5 Campaign Audit Logs ---")
        res = session.execute(text("SELECT id, campaign_id, status, message, created_at FROM campaign_audit_logs ORDER BY created_at DESC LIMIT 5"))
        for row in res:
            print(f"ID: {row[0]} | Campaign: {row[1]} | Status: {row[2]} | Msg: {row[3]} | At: {row[4]}")

        # Check post audit logs
        print("\n--- Latest 5 Post Audit Logs ---")
        res = session.execute(text("SELECT id, post_id, status, message, created_at FROM post_audit_logs ORDER BY created_at DESC LIMIT 5"))
        for row in res:
            print(f"ID: {row[0]} | Post: {row[1]} | Status: {row[2]} | Msg: {row[3]} | At: {row[4]}")

    except Exception as e:
        print(f"Error querying audit logs: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    check_audit_logs()
