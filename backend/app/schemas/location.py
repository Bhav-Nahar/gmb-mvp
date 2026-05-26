from datetime import datetime
from typing import Optional
from pydantic import BaseModel

class LocationSyncStatus(BaseModel):
    location_id: int
    status: str          # "Success", "Failed", "Pending"
    last_synced_at: Optional[datetime] = None
    error_message: Optional[str] = None
    run_type: str         # "Scheduled" or "Manual"

    class Config:
        from_attributes = True
