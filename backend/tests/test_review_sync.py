import os
import sys
import unittest
import datetime
from unittest.mock import patch, MagicMock, AsyncMock

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Resolve Celery import if not installed locally
import types

from app.db.session import Base
from app.models.organization import Organization
from app.models.user import User
from app.models.location import Location
from app.models.oauth_account import OAuthAccount
from app.models.review import Review
from app.models.organization_sync_state import OrganizationSyncState
from app.services.review_sync_service import ReviewSyncService, generate_content_hash
from app.providers.base.models import ReviewModel
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Map PostgreSQL JSONB to SQLite TEXT for in-memory test compilation compatibility
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB

@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(element, compiler, **kw):
    return "TEXT"

class ReviewSyncArchitectureTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
        self.db = self.SessionLocal()

        # Create Org
        self.org = Organization(id=1, name="Test Org")
        self.db.add(self.org)
        self.db.commit()

        # Create Owner User
        self.user = User(
            id=1,
            email="owner@testorg.com",
            name="Test User",
            google_id="test-google-id",
            role="Owner",
            is_active=True,
            organization_id=self.org.id
        )
        self.db.add(self.user)
        self.db.commit()

        # Create OAuthAccount so ProviderFactory works
        from app.core.security import encrypt_token
        self.oauth = OAuthAccount(
            id=1,
            user_id=self.user.id,
            provider="gbp",
            provider_account_id="mock_prov_acc_id",
            access_token=encrypt_token("mock_access_token"),
            refresh_token=encrypt_token("mock_refresh_token"),
            expires_at=datetime.datetime.utcnow() + datetime.timedelta(hours=1)
        )
        self.db.add(self.oauth)
        self.db.commit()

        # Create Location
        self.location = Location(
            id=1,
            organization_id=self.org.id,
            location_name="Test Location",
            google_location_id="locations/12345",
            google_account_id="accounts/67890",
            total_reviews=0,
            average_rating=0.0
        )
        self.db.add(self.location)

        # Create OrganizationSyncState
        self.sync_state = OrganizationSyncState(
            organization_id=self.org.id,
            location_sync_metadata={}
        )
        self.db.add(self.sync_state)
        self.db.commit()

        self.db.refresh(self.location)
        self.db.refresh(self.sync_state)

    def tearDown(self):
        self.db.close()

    @patch("app.providers.factory.ProviderFactory.get_provider")
    @patch("app.worker.celery.send_task")
    def test_sync_first_time_fetches_all_and_processes(self, mock_send_task, mock_get_provider):
        # Setup mock provider to return 2 reviews
        mock_provider = AsyncMock()
        mock_get_provider.return_value = mock_provider

        review_time_1 = datetime.datetime(2026, 6, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)
        review_time_2 = datetime.datetime(2026, 6, 2, 12, 0, 0, tzinfo=datetime.timezone.utc)

        mock_reviews = [
            ReviewModel(
                id="rev-1",
                location_id="locations/12345",
                reviewer_name="User A",
                rating=5,
                body="Awesome place!",
                reply="Thanks!",
                created_at=review_time_1,
                updated_at=review_time_1,
                provider="gbp"
            ),
            ReviewModel(
                id="rev-2",
                location_id="locations/12345",
                reviewer_name="User B",
                rating=3,
                body="Okay place.",
                reply=None,
                created_at=review_time_2,
                updated_at=review_time_2,
                provider="gbp"
            )
        ]
        mock_provider.get_reviews.return_value = mock_reviews

        # Execute
        import asyncio
        result = asyncio.run(ReviewSyncService.sync_location_reviews(self.db, self.location.id, "Scheduled"))
        
        # Verify reviews inserted in DB
        db_reviews = self.db.query(Review).all()
        self.assertEqual(len(db_reviews), 2)
        
        # Verify they have content hashes
        for rev in db_reviews:
            self.assertIsNotNone(rev.content_hash)
            self.assertIsNone(rev.sentiment_tagged_at) # Should be None to trigger sentiment task

        # Verify Celery enqueues both the sentiment-tagging and auto-reply tasks for the batch
        expected_kwargs = {"location_id": self.location.id, "organization_id": self.org.id}
        self.assertEqual(mock_send_task.call_count, 2)
        mock_send_task.assert_any_call("app.tasks.tag_reviews_sentiment_task", kwargs=expected_kwargs)
        mock_send_task.assert_any_call("app.tasks.auto_reply_reviews_task", kwargs=expected_kwargs)

        # Verify stats updated on location
        self.db.refresh(self.location)
        self.assertEqual(self.location.total_reviews, 2)
        self.assertEqual(self.location.average_rating, 4.0)

        # Verify OrganizationSyncState metadata is updated
        self.db.refresh(self.sync_state)
        metadata = self.sync_state.location_sync_metadata
        self.assertIn("loc_1", metadata)
        self.assertEqual(metadata["loc_1"]["last_review_sync_status"], "Success")
        # latest_review_update_at should be review_time_2 (iso format)
        self.assertEqual(metadata["loc_1"]["latest_review_update_at"], review_time_2.isoformat())

    @patch("app.providers.factory.ProviderFactory.get_provider")
    @patch("app.worker.celery.send_task")
    def test_sync_delta_updates_only_changed_reviews(self, mock_send_task, mock_get_provider):
        # Setup DB with 2 existing reviews
        review_time_1 = datetime.datetime(2026, 6, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)
        review_time_2 = datetime.datetime(2026, 6, 2, 12, 0, 0, tzinfo=datetime.timezone.utc)

        hash_1 = generate_content_hash(5, "Awesome place!", "Thanks!", review_time_1)
        hash_2 = generate_content_hash(3, "Okay place.", None, review_time_2)

        rev_1 = Review(
            organization_id=self.org.id,
            location_id=self.location.id,
            provider="gbp",
            provider_review_id="rev-1",
            reviewer_name="User A",
            rating=5,
            comment="Awesome place!",
            is_replied=True,
            reply_text="Thanks!",
            review_created_at=review_time_1,
            review_updated_at=review_time_1,
            content_hash=hash_1,
            sentiment_tagged_at=datetime.datetime.utcnow() # Already processed by AI
        )
        rev_2 = Review(
            organization_id=self.org.id,
            location_id=self.location.id,
            provider="gbp",
            provider_review_id="rev-2",
            reviewer_name="User B",
            rating=3,
            comment="Okay place.",
            is_replied=False,
            reply_text=None,
            review_created_at=review_time_2,
            review_updated_at=review_time_2,
            content_hash=hash_2,
            sentiment_tagged_at=datetime.datetime.utcnow() # Already processed by AI
        )
        self.db.add_all([rev_1, rev_2])
        self.db.commit()

        # Update metadata state
        self.sync_state.location_sync_metadata = {
            "loc_1": {
                "latest_review_update_at": review_time_2.isoformat(),
                "last_review_sync_completed_at": datetime.datetime.utcnow().isoformat(),
                "last_review_sync_status": "Success"
            }
        }
        self.db.commit()

        # Setup mock provider to return 3 reviews:
        # - rev-1: Unchanged
        # - rev-2: COMMENT CHANGED (Updated)
        # - rev-3: New review
        review_time_3 = datetime.datetime(2026, 6, 3, 12, 0, 0, tzinfo=datetime.timezone.utc)
        mock_provider = AsyncMock()
        mock_get_provider.return_value = mock_provider

        mock_reviews = [
            ReviewModel(
                id="rev-3", # New review
                location_id="locations/12345",
                reviewer_name="User C",
                rating=4,
                body="Pretty good",
                reply=None,
                created_at=review_time_3,
                updated_at=review_time_3,
                provider="gbp"
            ),
            ReviewModel(
                id="rev-2", # Updated comment
                location_id="locations/12345",
                reviewer_name="User B",
                rating=3,
                body="Actually, it was bad.", # changed
                reply=None,
                created_at=review_time_2,
                updated_at=review_time_2, # same update time, but hash differs
                provider="gbp"
            ),
            ReviewModel(
                id="rev-1", # Unchanged
                location_id="locations/12345",
                reviewer_name="User A",
                rating=5,
                body="Awesome place!",
                reply="Thanks!",
                created_at=review_time_1,
                updated_at=review_time_1,
                provider="gbp"
            )
        ]
        mock_provider.get_reviews.return_value = mock_reviews

        # Execute sync
        import asyncio
        result = asyncio.run(ReviewSyncService.sync_location_reviews(self.db, self.location.id, "Scheduled"))
        print("SYNC RESULT:", result)

        db_revs = self.db.query(Review).all()
        print("REVIEWS IN DB AFTER SYNC:")
        for r in db_revs:
            print(f"ID: {r.provider_review_id}, rating: {r.rating}, comment: {r.comment}, hash: {r.content_hash}, sentiment_tagged_at: {r.sentiment_tagged_at}")

        # Verify Celery enqueues both the sentiment-tagging and auto-reply tasks for the batch of updates
        expected_kwargs = {"location_id": self.location.id, "organization_id": self.org.id}
        self.assertEqual(mock_send_task.call_count, 2)
        mock_send_task.assert_any_call("app.tasks.tag_reviews_sentiment_task", kwargs=expected_kwargs)
        mock_send_task.assert_any_call("app.tasks.auto_reply_reviews_task", kwargs=expected_kwargs)
        
        # Verify database state
        self.db.refresh(rev_1)
        self.db.refresh(rev_2)
        
        # rev-1 was untouched, so sentiment_tagged_at is NOT None
        self.assertIsNotNone(rev_1.sentiment_tagged_at)
        
        # rev-2 comment is updated, and sentiment_tagged_at is reset to None
        self.assertEqual(rev_2.comment, "Actually, it was bad.")
        self.assertIsNone(rev_2.sentiment_tagged_at)

        # rev-3 is inserted
        rev_3 = self.db.query(Review).filter(Review.provider_review_id == "rev-3").first()
        self.assertIsNotNone(rev_3)
        self.assertEqual(rev_3.comment, "Pretty good")
        self.assertIsNone(rev_3.sentiment_tagged_at)

        # Verify metadata
        self.db.refresh(self.sync_state)
        metadata = self.sync_state.location_sync_metadata
        print("METADATA DICT IN TEST:", type(metadata), metadata)
        from sqlalchemy import text
        raw_val = self.db.execute(text("SELECT location_sync_metadata FROM organization_sync_states")).scalar()
        print("RAW VAL IN DB:", type(raw_val), raw_val)
        
        self.assertEqual(metadata["loc_1"]["latest_review_update_at"], review_time_3.isoformat())

if __name__ == "__main__":
    unittest.main()
