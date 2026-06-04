import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.session import SessionLocal
from app.models.location_edit import LocationEdit
from app.tasks import publish_listing_edit_task

# Run the task synchronously for edit ID 2
print("Running publish_listing_edit_task synchronously for edit ID 2...")
try:
    res = publish_listing_edit_task(edit_id=2, organization_id=1)
    print("Task result:", res)
except Exception as e:
    print("Exception during task execution:", e)
