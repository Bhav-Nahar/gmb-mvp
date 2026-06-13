"""Regression tests for per-user location-scope enforcement (horizontal privilege
escalation within an organization).

Each test sets up a Store Manager scoped to location A and asserts that acting on
location B (same org, but not assigned) raises HTTP 403 — covering the endpoints
hardened in the RBAC sweep: dynamic attributes, insights sync, billing unlock,
posts campaign filter/resume/cancel, and listing-edits list/activity.
"""
import os
import sys
import types
import asyncio
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB
from fastapi import HTTPException


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):
    return "TEXT"


sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Allow importing API modules without a real celery install.
try:
    import celery  # noqa: F401
except ImportError:
    if "celery" not in sys.modules:
        celery_stub = types.ModuleType("celery")

        def _shared_task(*args, **kwargs):
            return lambda fn: fn

        celery_stub.shared_task = _shared_task
        sys.modules["celery"] = celery_stub

from app.db.session import Base
from app.models.organization import Organization
from app.models.user import User
from app.models.location import Location
from app.models.user_location_access import UserLocationAccess
from app.models.post import Post
from app.models.campaign import Campaign
from app.models.publish_job import PublishJob
from app.core.roles import Role
from app.core.authorization import assert_location_access
from app.api import dynamic_attributes, insights, billing, posts, listing_edits


class LocationScopeRbacTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()

        self.org = Organization(name="Acme")
        self.db.add(self.org)
        self.db.commit()
        self.db.refresh(self.org)

        # Two locations in the same org.
        self.loc_a = Location(
            organization_id=self.org.id,
            google_location_id="locations/a",
            location_name="A",
            sync_status="Synced",
        )
        self.loc_b = Location(
            organization_id=self.org.id,
            google_location_id="locations/b",
            location_name="B",
            sync_status="Synced",
        )
        self.db.add_all([self.loc_a, self.loc_b])
        self.db.commit()
        self.db.refresh(self.loc_a)
        self.db.refresh(self.loc_b)

        # Store Manager assigned ONLY to location A.
        self.store = User(
            email="store@acme.com",
            name="Store",
            google_id="store-gid",
            role=Role.STORE_MANAGER,
            is_active=True,
            organization_id=self.org.id,
        )
        self.db.add(self.store)
        self.db.commit()
        self.db.refresh(self.store)
        self.db.add(UserLocationAccess(user_id=self.store.id, location_id=self.loc_a.id))
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def _assert_forbidden(self, callable_):
        with self.assertRaises(HTTPException) as ctx:
            callable_()
        self.assertEqual(ctx.exception.status_code, 403)

    # --- positive control -------------------------------------------------
    def test_assigned_location_is_allowed(self):
        # The assigned location must NOT raise.
        self.assertEqual(
            assert_location_access(self.db, self.store, self.loc_a.id),
            self.loc_a.id,
        )

    # --- dynamic attributes ----------------------------------------------
    def test_dynamic_attributes_form_schema_blocks_foreign_location(self):
        self._assert_forbidden(
            lambda: asyncio.run(
                dynamic_attributes.get_form_schema(
                    location_id=self.loc_b.id, db=self.db, current_user=self.store
                )
            )
        )

    # --- insights sync ----------------------------------------------------
    def test_insights_location_sync_blocks_foreign_location(self):
        self._assert_forbidden(
            lambda: insights.trigger_insights_sync(
                id=self.loc_b.id, current_user=self.store, db=self.db
            )
        )

    def test_insights_sync_all_blocks_restricted_user(self):
        self._assert_forbidden(
            lambda: insights.trigger_global_insights_sync(
                current_user=self.store, db=self.db
            )
        )

    # --- billing unlock (cross-org IDOR) ----------------------------------
    def test_billing_unlock_blocks_cross_org_location(self):
        # An admin of org1 must not be able to unlock a location in org2.
        org2 = Organization(name="Other")
        self.db.add(org2)
        self.db.commit()
        self.db.refresh(org2)
        foreign_loc = Location(
            organization_id=org2.id,
            google_location_id="locations/foreign",
            location_name="Foreign",
            sync_status="Synced",
        )
        self.db.add(foreign_loc)
        self.db.commit()
        self.db.refresh(foreign_loc)

        admin = User(
            email="admin@acme.com",
            name="Admin",
            google_id="admin-gid",
            role=Role.ADMIN,
            is_active=True,
            organization_id=self.org.id,
        )
        self.db.add(admin)
        self.db.commit()
        self.db.refresh(admin)

        req = billing.UnlockLocationsRequest(location_ids=[foreign_loc.id])
        self._assert_forbidden(
            lambda: billing.unlock_locations(
                request=req, db=self.db, current_user=admin, _=admin
            )
        )

    # --- posts: campaign list filter --------------------------------------
    def test_posts_list_campaigns_blocks_foreign_location(self):
        self._assert_forbidden(
            lambda: posts.list_campaigns(
                location_id=self.loc_b.id, db=self.db, current_user=self.store
            )
        )

    # --- posts: campaign resume / cancel ----------------------------------
    def _make_paused_campaign_at_loc_b(self, status):
        post = Post(organization_id=self.org.id, summary="hi")
        campaign = Campaign(organization_id=self.org.id, name="C", status=status)
        self.db.add_all([post, campaign])
        self.db.commit()
        self.db.refresh(post)
        self.db.refresh(campaign)
        job = PublishJob(
            organization_id=self.org.id,
            campaign_id=campaign.id,
            post_id=post.id,
            location_id=self.loc_b.id,
            status="Paused",
        )
        self.db.add(job)
        self.db.commit()
        return campaign

    def test_posts_resume_campaign_blocks_foreign_location(self):
        campaign = self._make_paused_campaign_at_loc_b("Paused")
        self._assert_forbidden(
            lambda: posts.resume_campaign(
                id=campaign.id, db=self.db, current_user=self.store
            )
        )

    def test_posts_cancel_campaign_blocks_foreign_location(self):
        campaign = self._make_paused_campaign_at_loc_b("Processing")
        self._assert_forbidden(
            lambda: posts.cancel_campaign(
                id=campaign.id, db=self.db, current_user=self.store
            )
        )

    # --- listing edits: list + activity -----------------------------------
    def test_listing_edits_list_blocks_foreign_location(self):
        self._assert_forbidden(
            lambda: listing_edits.list_edits(
                location_id=self.loc_b.id, db=self.db, current_user=self.store
            )
        )

    def test_listing_edits_activity_blocks_foreign_location(self):
        self._assert_forbidden(
            lambda: listing_edits.get_activity_log(
                location_id=self.loc_b.id, db=self.db, current_user=self.store
            )
        )


if __name__ == "__main__":
    unittest.main()
