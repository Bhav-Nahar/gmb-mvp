from sqlalchemy.orm import Session
from typing import Optional, Any
from app.models.activity_log import ActivityLog


class ActivityLogService:

    @staticmethod
    def log(
        db: Session,
        *,
        organization_id: int,
        entity_type: str,
        action: str,
        location_id: Optional[int] = None,
        actor_user_id: Optional[int] = None,
        entity_id: Optional[int] = None,
        payload: Optional[dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ) -> ActivityLog:
        """
        Insert one activity log row. Always call db.flush() after so the row
        gets an id within the current transaction — do NOT call db.commit() here.
        The caller owns the transaction.
        """
        entry = ActivityLog(
            organization_id=organization_id,
            location_id=location_id,
            actor_user_id=actor_user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            payload=payload or {},
            correlation_id=correlation_id,
        )
        db.add(entry)
        db.flush()
        return entry
