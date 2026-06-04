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

    def test_provider_mapper_import_smoke(self):
        import app.providers.gbp.mapper as mapper_module
        self.assertIsNotNone(mapper_module.GBPLocationMapper)

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
        self.assertEqual(task_args[2], "Manual")

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
