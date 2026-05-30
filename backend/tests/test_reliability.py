import os
import sys
import unittest
import datetime
from datetime import timezone
from unittest.mock import patch, MagicMock
from fastapi import HTTPException

# Map PostgreSQL JSONB to SQLite TEXT for in-memory compatibility
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB

@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(element, compiler, **kw):
    return "TEXT"

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import Base
from app.models.organization import Organization
from app.models.user import User
from app.models.post import Post
from app.models.location import Location
from app.models.post_media import PostMedia
from app.models.publish_job import PublishJob
from app.models.post_audit_log import PostAuditLog
from app.constants.posts import PostStatus, PublishJobStatus
from app.services.post_service import post_service
from app.tasks import process_publish_job_task

class ReliabilityGuardrailsTests(unittest.TestCase):
    def setUp(self):
        from app.db.session import engine, SessionLocal
        self.engine = engine
        Base.metadata.create_all(self.engine)
        self.SessionLocal = SessionLocal
        self.db = self.SessionLocal()

        # Clean up any leftover test data
        self.db.query(PublishJob).delete()
        self.db.query(PostAuditLog).delete()
        self.db.query(PostMedia).delete()
        self.db.query(Location).delete()
        self.db.query(Post).delete()
        self.db.query(User).delete()
        self.db.query(Organization).delete()
        self.db.commit()

        # Setup standard organization & users
        self.org = Organization(name="Test Org")
        self.db.add(self.org)
        self.db.commit()
        self.db.refresh(self.org)

        self.user = User(
            email="owner@test.com",
            name="Owner",
            google_id="gid-test",
            role="Owner",
            is_active=True,
            organization_id=self.org.id
        )
        self.db.add(self.user)
        
        # Setup target location
        self.location = Location(
            organization_id=self.org.id,
            google_location_id="locations/loc123",
            location_name="Storefront Bellevue",
            sync_status="Synced"
        )
        self.db.add(self.location)
        self.db.commit()
        self.db.refresh(self.user)
        self.db.refresh(self.location)

    def tearDown(self):
        self.db.close()

    def test_unapproved_status_publishing_block(self):
        # 1. Create a draft post
        post = Post(
            organization_id=self.org.id,
            title="Draft Post",
            summary="A beautiful local post draft",
            status="Draft",
            post_type="UPDATE"
        )
        self.db.add(post)
        self.db.commit()
        self.db.refresh(post)

        # 2. Attempting to publish must yield a 409 Conflict
        with self.assertRaises(HTTPException) as ctx:
            post_service.publish_post_to_location(
                db=self.db,
                post_id=post.id,
                location_id=self.location.id,
                organization_id=self.org.id,
                user_id=self.user.id
            )
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertIn("Only APPROVED posts can be published", ctx.exception.detail)

    def test_media_validation_optimized_url_block(self):
        # 1. Create an Approved post but with NO media
        post = Post(
            organization_id=self.org.id,
            title="Approved Post",
            summary="A beautiful approved post",
            status="Approved",
            post_type="UPDATE"
        )
        self.db.add(post)
        self.db.commit()
        self.db.refresh(post)

        # 2. Attempting to publish without media yields 400 Bad Request
        with self.assertRaises(HTTPException) as ctx:
            post_service.publish_post_to_location(
                db=self.db,
                post_id=post.id,
                location_id=self.location.id,
                organization_id=self.org.id,
                user_id=self.user.id
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Post must have at least one validated media", ctx.exception.detail)

        # 3. Add an UNOPTIMIZED or INVALID media
        media = PostMedia(
            organization_id=self.org.id,
            post_id=post.id,
            storage_provider="local",
            storage_key="org/media.jpg",
            media_type="PHOTO",
            sha256_hash="hash123",
            cdn_url="http://localhost:8000/media.jpg",
            upload_status="Uploaded",
            validation_status="Invalid"  # Invalid!
        )
        self.db.add(media)
        self.db.commit()

        # 4. Should still fail because validation_status is Invalid
        with self.assertRaises(HTTPException) as ctx:
            post_service.publish_post_to_location(
                db=self.db,
                post_id=post.id,
                location_id=self.location.id,
                organization_id=self.org.id,
                user_id=self.user.id
            )
        self.assertEqual(ctx.exception.status_code, 400)

    @patch("app.tasks.process_publish_job_task.delay")
    def test_active_job_concurrency_deduplication(self, mock_celery):
        # 1. Create an Approved post with valid optimized media
        post = Post(
            organization_id=self.org.id,
            title="Approved Post",
            summary="Approved with valid media",
            status="Approved",
            post_type="UPDATE"
        )
        self.db.add(post)
        self.db.flush()

        media = PostMedia(
            organization_id=self.org.id,
            post_id=post.id,
            storage_provider="local",
            storage_key="org/media.jpg",
            media_type="PHOTO",
            sha256_hash="hash123",
            cdn_url="http://localhost:8000/media.jpg",
            optimized_url="http://localhost:8000/media_optimized.jpg", # Optimized!
            upload_status="Uploaded",
            validation_status="Valid" # Valid!
        )
        self.db.add(media)
        self.db.commit()

        # 2. First Publish: should succeed and create a PENDING job
        job_1 = post_service.publish_post_to_location(
            db=self.db,
            post_id=post.id,
            location_id=self.location.id,
            organization_id=self.org.id,
            user_id=self.user.id
        )
        self.assertEqual(job_1.status.upper(), "PENDING")
        self.assertEqual(mock_celery.call_count, 1)

        # Reset post status to Approved so the second call passes eligibility checks
        post.status = "Approved"
        self.db.commit()

        # 3. Second Publish: since job is already active, return the existing job ID immediately
        job_2 = post_service.publish_post_to_location(
            db=self.db,
            post_id=post.id,
            location_id=self.location.id,
            organization_id=self.org.id,
            user_id=self.user.id
        )
        self.assertEqual(job_2.id, job_1.id)
        # Celery must NOT be invoked a second time
        self.assertEqual(mock_celery.call_count, 1)

    @patch("redis.Redis.from_url")
    @patch("app.providers.factory.ProviderFactory.get_provider")
    def test_worker_success_state_transitions(self, mock_get_provider, mock_redis):
        # Setup mocks
        mock_lock = MagicMock()
        mock_lock.acquire.return_value = True
        mock_redis.return_value.lock.return_value = mock_lock

        mock_res = MagicMock()
        mock_res.id = "google_post_id_abc123"
        mock_res.provider_metadata = {"status": "live", "name": "google_post_id_abc123"}
        
        async def mock_create_post(loc_id, payload):
            return mock_res
        
        mock_provider = MagicMock()
        mock_provider.create_post = mock_create_post
        mock_get_provider.return_value = mock_provider

        # 1. Create a Post in PUBLISHING state and a PublishJob in PENDING state
        post = Post(
            organization_id=self.org.id,
            title="Publishing Post",
            summary="A post currently publishing",
            status="Publishing",
            post_type="UPDATE"
        )
        self.db.add(post)
        self.db.flush()

        job = PublishJob(
            organization_id=self.org.id,
            post_id=post.id,
            location_id=self.location.id,
            status="Pending",
            idempotency_key="key_123"
        )
        self.db.add(job)
        self.db.commit()

        # 2. Run the Celery task synchronously via underlying __wrapped__ function
        process_publish_job_task.__wrapped__(job.id, self.org.id)

        # 3. Verify state updates
        self.db.refresh(job)
        self.db.refresh(post)

        self.assertEqual(job.status.upper(), "SUCCESS")
        self.assertEqual(job.google_post_id, "google_post_id_abc123")
        self.assertEqual(job.provider_response["status"], "live")
        self.assertEqual(post.status.upper(), "PUBLISHED")

        # Verify Audit Log was generated
        audit = self.db.query(PostAuditLog).filter(PostAuditLog.post_id == post.id, PostAuditLog.action == "PUBLISHED").first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.new_status.upper(), "PUBLISHED")

if __name__ == "__main__":
    unittest.main()
