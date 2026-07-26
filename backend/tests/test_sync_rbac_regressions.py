import os
import sys
import unittest
import types
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from starlette.requests import Request
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


# Map PostgreSQL JSONB to SQLite TEXT for in-memory test compilation compatibility
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB

@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(element, compiler, **kw):
    return "TEXT"

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Allow tests to import API modules even when celery is not installed locally.
try:
    import celery
except ImportError:
    if "celery" not in sys.modules:
        celery_stub = types.ModuleType("celery")
        celery_schedules_stub = types.ModuleType("celery.schedules")

        class _StubCelery:
            def __init__(self, *args, **kwargs):
                self.conf = types.SimpleNamespace(beat_schedule={}, timezone="UTC")

            def send_task(self, *args, **kwargs):
                return type("T", (), {"id": "stub-task"})()

            def autodiscover_tasks(self, *args, **kwargs):
                return None

        def _shared_task(*args, **kwargs):
            def _decorator(fn):
                return fn

            return _decorator

        def _crontab(*args, **kwargs):
            return None

        celery_stub.Celery = _StubCelery
        celery_stub.shared_task = _shared_task
        celery_schedules_stub.crontab = _crontab
        sys.modules["celery"] = celery_stub
        sys.modules["celery.schedules"] = celery_schedules_stub

from app.db.session import Base
from app.models.organization import Organization
from app.models.user import User
from app.models.oauth_account import OAuthAccount
from app.models.location import Location
from app.models.user_location_access import UserLocationAccess
from app.models.organization_sync_state import OrganizationSyncState
from app.api import locations as locations_api
from app.api import auth as auth_api


def build_request_with_cookie(cookie_value: str) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/auth/google/callback",
        "headers": [(b"cookie", f"oauth_state={cookie_value}".encode())],
        "query_string": b"",
    }
    return Request(scope)


class SyncAndRbacRegressionTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
        self.db = self.SessionLocal()

        self.org = Organization(name="Acme")
        self.db.add(self.org)
        self.db.commit()
        self.db.refresh(self.org)

    def tearDown(self):
        self.db.close()

    def test_provider_mapper_location_state(self):
        from app.providers.gbp.mapper import GBPLocationMapper
        from app.providers.gbp.schemas import GBPLocationRaw
        
        # Test case 1: verified location
        raw_verified = GBPLocationRaw(
            name="locations/mock-1",
            title="Mock Verified",
            locationState={"isVerified": True, "isSuspended": False, "isDuplicate": False}
        )
        model_verified = GBPLocationMapper.to_model(raw_verified)
        self.assertTrue(model_verified.is_verified)
        self.assertFalse(model_verified.is_suspended)
        self.assertFalse(model_verified.is_duplicate)
        
        # Test case 2: suspended duplicate location
        raw_suspended = GBPLocationRaw(
            name="locations/mock-2",
            title="Mock Suspended Duplicate",
            locationState={"isVerified": False, "isSuspended": True, "isDuplicate": True}
        )
        model_suspended = GBPLocationMapper.to_model(raw_suspended)
        self.assertFalse(model_suspended.is_verified)
        self.assertTrue(model_suspended.is_suspended)
        self.assertTrue(model_suspended.is_duplicate)
        
        # Test case 3: missing locationState
        raw_missing = GBPLocationRaw(
            name="locations/mock-3",
            title="Mock Missing State"
        )
        model_missing = GBPLocationMapper.to_model(raw_missing)
        self.assertIsNone(model_missing.is_verified)
        self.assertIsNone(model_missing.is_suspended)
        self.assertIsNone(model_missing.is_duplicate)

    def test_location_sync_selects_active_owner_admin_with_latest_token(self):
        owner = User(
            email="owner@acme.com",
            name="Owner",
            google_id="owner-gid",
            role="Owner",
            is_active=True,
            organization_id=self.org.id,
        )
        admin = User(
            email="admin@acme.com",
            name="Admin",
            google_id="admin-gid",
            role="Admin",
            is_active=True,
            organization_id=self.org.id,
        )
        store = User(
            email="store@acme.com",
            name="Store",
            google_id="store-gid",
            role="Store Manager",
            is_active=True,
            organization_id=self.org.id,
        )
        self.db.add_all([owner, admin, store])
        self.db.commit()
        self.db.refresh(owner)
        self.db.refresh(admin)
        self.db.refresh(store)

        self.db.add_all(
            [
                OAuthAccount(
                    user_id=owner.id,
                    provider="gbp",
                    provider_account_id="owner-gid",
                    access_token="x",
                    refresh_token="y",
                    expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
                ),
                OAuthAccount(
                    user_id=admin.id,
                    provider="gbp",
                    provider_account_id="admin-gid",
                    access_token="x",
                    refresh_token="y",
                    expires_at=datetime.now(timezone.utc) + timedelta(minutes=90),
                ),
                OAuthAccount(
                    user_id=store.id,
                    provider="gbp",
                    provider_account_id="store-gid",
                    access_token="x",
                    refresh_token="y",
                    expires_at=datetime.now(timezone.utc) + timedelta(minutes=120),
                ),
            ]
        )
        self.db.commit()

        with patch.object(locations_api.celery, "send_task") as send_task:
            send_task.return_value = type("T", (), {"id": "task-1"})()
            response = locations_api.trigger_sync(db=self.db, current_user=owner)

        self.assertEqual(response["message"], "Sync task has been queued in the background.")
        args = send_task.call_args.kwargs["args"]
        self.assertEqual(args[0], self.org.id)
        self.assertEqual(args[1], admin.id)
        self.assertEqual(args[2], "Manual")

    def test_existing_user_login_queues_sync(self):
        user = User(
            email="existing@acme.com",
            name="Existing User",
            google_id="google_id_existing",
            role="Owner",
            is_active=True,
            organization_id=self.org.id,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)

        self.db.add(
            OAuthAccount(
                user_id=user.id,
                provider="gbp",
                provider_account_id="google_id_existing",
                access_token="enc-old",
                refresh_token="enc-old-refresh",
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
            )
        )
        self.db.commit()

        with patch.object(auth_api.ProviderFactory, "exchange_code_for_tokens") as exchange_tokens, patch.object(
            auth_api, "encrypt_token"
        ) as encrypt_token, patch.object(auth_api.celery, "send_task") as send_task:
            exchange_tokens.return_value = {
                "access_token": "mock_access_token_abc",
                "refresh_token": "mock_refresh_token_def",
                "expires_in": 3600,
                "email": "existing@acme.com",
            }
            encrypt_token.side_effect = lambda v: f"enc:{v}" if v else None
            send_task.return_value = type("T", (), {"id": "task-2"})()

            request = build_request_with_cookie("csrf123")
            result = auth_api.google_callback(
                request=request,
                code="dummy-code",
                state="csrf123:",
                db=self.db,
            )

        self.assertEqual(result.status_code, 307)
        send_task.assert_called_once()
        task_args = send_task.call_args.kwargs["args"]
        self.assertEqual(task_args[0], self.org.id)
        self.assertEqual(task_args[1], user.id)
        self.assertEqual(task_args[2], "Onboarding")

    def test_login_relinks_account_whose_google_id_changed(self):
        """A stale google_id must not fall through to the create path.

        The lookup is by google_id alone, but users.email is UNIQUE — so a row
        recreated by hand (or a re-issued Google `sub`) used to hit an IntegrityError
        on insert and lock the person out. The verified email relinks it instead.
        """
        user = User(
            email="relink@acme.com",
            name="Relink User",
            google_id="stale_sub_from_old_row",
            role="Owner",
            is_active=True,
            organization_id=self.org.id,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        original_id = user.id

        with patch.object(auth_api.ProviderFactory, "exchange_code_for_tokens") as exchange_tokens, patch.object(
            auth_api, "encrypt_token"
        ) as encrypt_token, patch.object(auth_api.celery, "send_task") as send_task:
            exchange_tokens.return_value = {
                "access_token": "mock_access_token_abc",
                "refresh_token": "mock_refresh_token_def",
                "expires_in": 3600,
                "email": "relink@acme.com",
            }
            encrypt_token.side_effect = lambda v: f"enc:{v}" if v else None
            send_task.return_value = type("T", (), {"id": "task-3"})()

            result = auth_api.google_callback(
                request=build_request_with_cookie("csrf123"),
                code="dummy-code",
                state="csrf123:",
                db=self.db,
            )

        self.assertEqual(result.status_code, 307)  # logged in, not an error redirect
        self.db.expire_all()
        rows = self.db.query(User).filter(User.email == "relink@acme.com").all()
        self.assertEqual(len(rows), 1)               # no duplicate row, no new workspace
        self.assertEqual(rows[0].id, original_id)    # same account, same org data
        self.assertEqual(rows[0].google_id, "google_id_relink")  # relinked to the new sub
        self.assertEqual(self.db.query(Organization).count(), 1)

    def test_login_does_not_queue_sync_when_fresh(self):
        user = User(
            email="fresh@acme.com",
            name="Fresh User",
            google_id="google_id_fresh",
            role="Owner",
            is_active=True,
            organization_id=self.org.id,
        )
        self.db.add(user)
        # Create a fresh sync state (sync completed 1 hour ago)
        sync_state = OrganizationSyncState(
            organization_id=self.org.id,
            last_location_sync_at=datetime.now(timezone.utc) - timedelta(hours=1),
            sync_in_progress=False,
            last_sync_status="Success"
        )
        self.db.add(sync_state)
        self.db.commit()

        self.db.add(
            OAuthAccount(
                user_id=user.id,
                provider="gbp",
                provider_account_id="google_id_fresh",
                access_token="enc-old",
                refresh_token="enc-old-refresh",
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
            )
        )
        self.db.commit()

        with patch.object(auth_api.ProviderFactory, "exchange_code_for_tokens") as exchange_tokens, patch.object(
            auth_api, "encrypt_token"
        ) as encrypt_token, patch.object(auth_api.celery, "send_task") as send_task:
            exchange_tokens.return_value = {
                "access_token": "mock_access_token_abc",
                "refresh_token": "mock_refresh_token_def",
                "expires_in": 3600,
                "email": "fresh@acme.com",
            }
            encrypt_token.side_effect = lambda v: f"enc:{v}" if v else None
            send_task.return_value = type("T", (), {"id": "task-3"})()

            request = build_request_with_cookie("csrf123")
            result = auth_api.google_callback(
                request=request,
                code="dummy-code",
                state="csrf123:",
                db=self.db,
            )

        self.assertEqual(result.status_code, 307)
        send_task.assert_not_called()

    def test_login_queues_sync_when_stale(self):
        user = User(
            email="stale@acme.com",
            name="Stale User",
            google_id="google_id_stale",
            role="Owner",
            is_active=True,
            organization_id=self.org.id,
        )
        self.db.add(user)
        # Create a stale sync state (sync completed 13 hours ago)
        sync_state = OrganizationSyncState(
            organization_id=self.org.id,
            last_location_sync_at=datetime.now(timezone.utc) - timedelta(hours=13),
            sync_in_progress=False,
            last_sync_status="Success"
        )
        self.db.add(sync_state)
        self.db.commit()

        self.db.add(
            OAuthAccount(
                user_id=user.id,
                provider="gbp",
                provider_account_id="google_id_stale",
                access_token="enc-old",
                refresh_token="enc-old-refresh",
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
            )
        )
        self.db.commit()

        with patch.object(auth_api.ProviderFactory, "exchange_code_for_tokens") as exchange_tokens, patch.object(
            auth_api, "encrypt_token"
        ) as encrypt_token, patch.object(auth_api.celery, "send_task") as send_task:
            exchange_tokens.return_value = {
                "access_token": "mock_access_token_abc",
                "refresh_token": "mock_refresh_token_def",
                "expires_in": 3600,
                "email": "stale@acme.com",
            }
            encrypt_token.side_effect = lambda v: f"enc:{v}" if v else None
            send_task.return_value = type("T", (), {"id": "task-4"})()

            request = build_request_with_cookie("csrf123")
            result = auth_api.google_callback(
                request=request,
                code="dummy-code",
                state="csrf123:",
                db=self.db,
            )

        self.assertEqual(result.status_code, 307)
        send_task.assert_called_once()
        task_args = send_task.call_args.kwargs["args"]
        self.assertEqual(task_args[0], self.org.id)
        self.assertEqual(task_args[1], user.id)
        self.assertEqual(task_args[2], "Auto-Refresh")

    def test_login_does_not_queue_sync_when_already_in_progress(self):
        """Guard: if sync_in_progress=True and NOT stuck, login must NOT dispatch a new task."""
        user = User(
            email="inprogress@acme.com",
            name="InProgress User",
            google_id="google_id_inprogress",
            role="Owner",
            is_active=True,
            organization_id=self.org.id,
        )
        self.db.add(user)
        # Sync started just 30 minutes ago — still within the 2h stuck threshold.
        sync_state = OrganizationSyncState(
            organization_id=self.org.id,
            last_location_sync_at=datetime.now(timezone.utc) - timedelta(hours=13),
            sync_in_progress=True,
            sync_started_at=datetime.now(timezone.utc) - timedelta(minutes=30),
            last_sync_status="Pending"
        )
        self.db.add(sync_state)
        self.db.commit()

        self.db.add(
            OAuthAccount(
                user_id=user.id,
                provider="gbp",
                provider_account_id="google_id_inprogress",
                access_token="enc-old",
                refresh_token="enc-old-refresh",
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
            )
        )
        self.db.commit()

        with patch.object(auth_api.ProviderFactory, "exchange_code_for_tokens") as exchange_tokens, \
             patch.object(auth_api, "encrypt_token") as encrypt_token, \
             patch.object(auth_api.celery, "send_task") as send_task:
            exchange_tokens.return_value = {
                "access_token": "mock_access_token_abc",
                "refresh_token": "mock_refresh_token_def",
                "expires_in": 3600,
                "email": "inprogress@acme.com",
            }
            encrypt_token.side_effect = lambda v: f"enc:{v}" if v else None

            request = build_request_with_cookie("csrf123")
            result = auth_api.google_callback(
                request=request,
                code="dummy-code",
                state="csrf123:",
                db=self.db,
            )

        self.assertEqual(result.status_code, 307)
        # Must NOT dispatch — a healthy sync is already running.
        send_task.assert_not_called()

    def test_login_resets_stuck_sync_and_queues_new_task(self):
        """Recovery: if sync_in_progress=True but sync_started_at is >2h ago (worker crashed),
        login must auto-recover and dispatch a fresh Auto-Refresh task."""
        user = User(
            email="stuck@acme.com",
            name="Stuck User",
            google_id="google_id_stuck",
            role="Owner",
            is_active=True,
            organization_id=self.org.id,
        )
        self.db.add(user)
        # Simulate a worker crash: sync_in_progress=True but started 3 hours ago.
        sync_state = OrganizationSyncState(
            organization_id=self.org.id,
            last_location_sync_at=datetime.now(timezone.utc) - timedelta(hours=13),
            sync_in_progress=True,
            sync_started_at=datetime.now(timezone.utc) - timedelta(hours=3),
            last_sync_status="Pending"
        )
        self.db.add(sync_state)
        self.db.commit()

        self.db.add(
            OAuthAccount(
                user_id=user.id,
                provider="gbp",
                provider_account_id="google_id_stuck",
                access_token="enc-old",
                refresh_token="enc-old-refresh",
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
            )
        )
        self.db.commit()

        with patch.object(auth_api.ProviderFactory, "exchange_code_for_tokens") as exchange_tokens, \
             patch.object(auth_api, "encrypt_token") as encrypt_token, \
             patch.object(auth_api.celery, "send_task") as send_task:
            exchange_tokens.return_value ={
                "access_token": "mock_access_token_abc",
                "refresh_token": "mock_refresh_token_def",
                "expires_in": 3600,
                "email": "stuck@acme.com",
            }
            encrypt_token.side_effect = lambda v: f"enc:{v}" if v else None
            send_task.return_value = type("T", (), {"id": "task-stuck"})()

            request = build_request_with_cookie("csrf123")
            result = auth_api.google_callback(
                request=request,
                code="dummy-code",
                state="csrf123:",
                db=self.db,
            )

        self.assertEqual(result.status_code, 307)
        # Must dispatch — the orphaned state was detected and auto-recovered.
        send_task.assert_called_once()
        task_args = send_task.call_args.kwargs["args"]
        self.assertEqual(task_args[2], "Auto-Refresh")


    def test_store_manager_location_scope_enforced(self):
        store = User(
            email="store2@acme.com",
            name="Store Two",
            google_id="store2-gid",
            role="Store Manager",
            is_active=True,
            organization_id=self.org.id,
        )
        self.db.add(store)
        self.db.commit()
        self.db.refresh(store)

        loc_a = Location(
            organization_id=self.org.id,
            google_location_id="locations/a",
            location_name="A",
            sync_status="Synced",
        )
        loc_b = Location(
            organization_id=self.org.id,
            google_location_id="locations/b",
            location_name="B",
            sync_status="Synced",
        )
        self.db.add_all([loc_a, loc_b])
        self.db.commit()
        self.db.refresh(loc_a)
        self.db.refresh(loc_b)

        self.db.add(UserLocationAccess(user_id=store.id, location_id=loc_a.id))
        self.db.commit()

        from app.api.deps import get_user_location_ids

        allowed = get_user_location_ids(store, self.db)
        self.assertIn(loc_a.id, allowed)
        self.assertNotIn(loc_b.id, allowed)


if __name__ == "__main__":
    unittest.main()
