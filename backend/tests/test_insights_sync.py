import os
import sys
import unittest
import types
import datetime
from unittest.mock import patch

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


from app.db.session import Base
from app.models.organization import Organization
from app.models.user import User
from app.models.location import Location
from app.models.organization_sync_state import OrganizationSyncState
from app.api import insights as insights_api
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Map PostgreSQL JSONB to SQLite TEXT for in-memory test compilation compatibility
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB

@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(element, compiler, **kw):
    return "TEXT"

class InsightsSyncArchitectureTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
        self.db = self.SessionLocal()

        self.org = Organization(name="Test Org")
        self.db.add(self.org)
        self.db.commit()
        self.db.refresh(self.org)

        self.user = User(
            email="user@testorg.com",
            name="Test User",
            google_id="test-google-id",
            role="Owner",
            is_active=True,
            organization_id=self.org.id
        )
        self.db.add(self.user)
        self.db.commit()
        self.db.refresh(self.user)

    def tearDown(self):
        self.db.close()

    def test_sync_status_when_never_synced(self):
        response = insights_api.get_insights_sync_status(current_user=self.user, db=self.db)
        self.assertEqual(response["insights_sync_in_progress"], False)
        self.assertEqual(response["last_insights_sync_status"], "never_synced")
        self.assertIsNone(response["last_insights_sync_at"])

    def test_stale_logic_triggers_sync_automatically(self):
        with patch.object(insights_api.celery, "send_task") as send_task:
            send_task.return_value = type("T", (), {"id": "test-task"})()
            
            # 1. No sync state should trigger sync
            insights_api.check_and_trigger_stale_insights_sync(self.org.id, self.db)
            send_task.assert_called_once()
            
            send_task.reset_mock()
            
            # 2. Fresh sync state should NOT trigger sync
            sync_state = OrganizationSyncState(
                organization_id=self.org.id,
                last_insights_sync_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=5),
                insights_sync_in_progress=False,
                last_insights_sync_status="success"
            )
            self.db.add(sync_state)
            self.db.commit()
            
            insights_api.check_and_trigger_stale_insights_sync(self.org.id, self.db)
            send_task.assert_not_called()

            # 3. Stale sync state (>24h) should trigger sync
            sync_state.last_insights_sync_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=25)
            self.db.commit()
            
            insights_api.check_and_trigger_stale_insights_sync(self.org.id, self.db)
            send_task.assert_called_once()

    def test_manual_sync_all_endpoint_forces_sync(self):
        sync_state = OrganizationSyncState(
            organization_id=self.org.id,
            last_insights_sync_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1),
            insights_sync_in_progress=False,
            last_insights_sync_status="success"
        )
        self.db.add(sync_state)
        self.db.commit()

        with patch.object(insights_api.celery, "send_task") as send_task:
            insights_api.trigger_global_insights_sync(force=True, current_user=self.user, db=self.db)
            # Even though last sync is fresh (1h ago), force parameter must trigger it
            send_task.assert_called_once()

    def test_stuck_sync_recovery(self):
        with patch.object(insights_api.celery, "send_task") as send_task:
            send_task.return_value = type("T", (), {"id": "test-task"})()
            
            # Create a sync state that is in progress but started >2 hours ago (stuck)
            sync_state = OrganizationSyncState(
                organization_id=self.org.id,
                last_insights_sync_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=25),
                insights_sync_in_progress=True,
                last_insights_sync_started_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=3),
                last_insights_sync_status="in_progress"
            )
            self.db.add(sync_state)
            self.db.commit()

            # The check should detect it as stuck and trigger a recovery sync
            insights_api.check_and_trigger_stale_insights_sync(self.org.id, self.db)
            send_task.assert_called_once()

    def test_in_progress_sync_prevents_duplicate(self):
        with patch.object(insights_api.celery, "send_task") as send_task:
            send_task.return_value = type("T", (), {"id": "test-task"})()
            
            # Create a sync state that is currently in progress and healthy (<2 hours)
            sync_state = OrganizationSyncState(
                organization_id=self.org.id,
                last_insights_sync_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=25),
                insights_sync_in_progress=True,
                last_insights_sync_started_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=30),
                last_insights_sync_status="in_progress"
            )
            self.db.add(sync_state)
            self.db.commit()

            # The check should NOT trigger because it is healthy and in progress
            insights_api.check_and_trigger_stale_insights_sync(self.org.id, self.db)
            send_task.assert_not_called()

if __name__ == "__main__":
    unittest.main()

