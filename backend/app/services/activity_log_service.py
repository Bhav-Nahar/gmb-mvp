import json
import logging
from sqlalchemy.orm import Session
from typing import Optional, Any
from app.models.activity_log import ActivityLog

logger = logging.getLogger(__name__)


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
        Stage one activity log row and flush it within the current transaction.

        This method only stages the entry — it does NOT call db.commit().
        Callers are responsible for committing the transaction after this method
        returns so that the activity log entry is persisted atomically with any
        surrounding changes.
        """
        safe_payload = payload or {}
        try:
            json.dumps(safe_payload)
        except (TypeError, ValueError):
            logger.warning(
                "ActivityLogService.log: payload for action=%s entity_type=%s is not JSON-serializable; "
                "storing raw string fallback.",
                action,
                entity_type,
            )
            safe_payload = {"_raw": str(payload)}

        entry = ActivityLog(
            organization_id=organization_id,
            location_id=location_id,
            actor_user_id=actor_user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            payload=safe_payload,
            correlation_id=correlation_id,
        )
        db.add(entry)
        db.flush()
        return entry
