import os
import sys
import unittest
import datetime
from unittest.mock import patch, MagicMock

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB

@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(element, compiler, **kw):
    return "TEXT"

# Setup Celery Stub
import types
try:
    import celery
    if not hasattr(celery, "shared_task"):
        celery.shared_task = lambda *args, **kwargs: lambda fn: fn
except ImportError:
    if "celery" not in sys.modules:
        celery_stub = types.ModuleType("celery")
        def _shared_task(*args, **kwargs):
            return lambda fn: fn
        celery_stub.shared_task = _shared_task
        celery_stub.Celery = MagicMock()
        sys.modules["celery"] = celery_stub

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.organization import Organization
from app.models.user import User
from app.models.location import Location
from app.models.oauth_account import OAuthAccount
from app.models.gbp_attribute_definition import GbpAttributeDefinition
from app.api.dynamic_attributes import get_form_schema
from app.api.locations import trigger_sync

class DynamicAttributesCacheTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
        self.db = self.SessionLocal()

        # Seed organization
        self.org = Organization(name="Acme Corp")
        self.db.add(self.org)
        self.db.commit()
        self.db.refresh(self.org)

        # Seed location
        self.location = Location(
            organization_id=self.org.id,
            google_location_id="locations/mock-loc-123",
            location_name="Acme Store",
            primary_category="Coffee Shop",
            sync_status="Synced",
            attention_needed=False
        )
        self.db.add(self.location)
        self.db.commit()
        self.db.refresh(self.location)

        # Seed definitions
        self.definition = GbpAttributeDefinition(
            category_id="gcid:coffee_shop",
            attribute_id="wifi",
            region_code="IN",
            language_code="en",
            display_name="Has Wifi",
            group_display_name="Amenities",
            value_type="BOOL",
            is_repeatable=False,
            options_json=[],
            is_active=True
        )
        self.db.add(self.definition)
        self.db.commit()

        # Seed user
        self.user = User(
            email="manager@acme.com",
            name="Store Manager",
            google_id="manager-g-id",
            role="Owner",
            is_active=True,
            organization_id=self.org.id
        )
        self.db.add(self.user)
        self.db.commit()
        self.db.refresh(self.user)

    def tearDown(self):
        self.db.close()

    @patch("app.api.dynamic_attributes.get_redis")
    def test_get_form_schema_caching(self, mock_get_redis):
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_redis.get.return_value = None  # Cache miss

        import asyncio
        # Call get_form_schema (async def) using asyncio.run
        response = asyncio.run(get_form_schema(
            location_id=self.location.id,
            db=self.db,
            current_user=self.user
        ))
        self.assertIsNotNone(response)
        self.assertIn("schema", response)
        mock_redis.setex.assert_called_once()

        # Test cache hit
        mock_redis.setex.reset_mock()
        mock_redis.get.return_value = '{"schema": [{"attribute_id": "wifi", "display_name": "Has Wifi"}]}'
        response_hit = asyncio.run(get_form_schema(
            location_id=self.location.id,
            db=self.db,
            current_user=self.user
        ))
        self.assertEqual(len(response_hit["schema"]), 1)
        self.assertEqual(response_hit["schema"][0]["attribute_id"], "wifi")
        mock_redis.setex.assert_not_called()

    @patch("app.api.locations.get_redis")
    @patch("app.api.locations.celery")
    def test_manual_sync_invalidates_cache(self, mock_celery, mock_get_redis):
        # Setup mock admin user with OAuth account to satisfy dependencies of locations/sync
        oauth = OAuthAccount(
            user_id=self.user.id,
            provider="google",
            provider_account_id="google-id-1234",
            expires_at=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1),
            access_token="valid_token",
            refresh_token="valid_refresh_token"
        )
        self.db.add(oauth)
        self.db.commit()

        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        trigger_sync(db=self.db, current_user=self.user)
        mock_redis.delete.assert_called_with(f"location:attributes_schema:{self.location.id}")

if __name__ == "__main__":
    import asyncio
    unittest.main()
