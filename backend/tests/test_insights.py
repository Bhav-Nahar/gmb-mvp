import os
import sys
import unittest
import datetime
from unittest.mock import patch, MagicMock

from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB

@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(element, compiler, **kw):
    return "TEXT"

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Setup Celery Stub
import types
try:
    import celery
except ImportError:
    if "celery" not in sys.modules:
        celery_stub = types.ModuleType("celery")
        def _shared_task(*args, **kwargs):
            return lambda fn: fn
        celery_stub.shared_task = _shared_task
        sys.modules["celery"] = celery_stub

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.organization import Organization
from app.models.user import User
from app.models.location import Location
from app.models.review import Review
from app.models.location_daily_insights import LocationDailyInsight
from app.services.insight_sync_service import InsightSyncService
from app.constants.attention import AttentionThresholds
from app.api.insights import calculate_delta, get_insights_overview, get_location_insights

class InsightsSystemTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
        self.db = self.SessionLocal()

        # Seed organization
        self.org = Organization(name="Acme Insights Corp")
        self.db.add(self.org)
        self.db.commit()
        self.db.refresh(self.org)

        # Seed location
        self.location = Location(
            organization_id=self.org.id,
            google_location_id="locations/mock-insight-loc-1",
            location_name="Acme Seattle Store",
            sync_status="Synced",
            attention_needed=False
        )
        self.db.add(self.location)
        self.db.commit()
        self.db.refresh(self.location)

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

    def test_calculate_delta(self):
        self.assertEqual(calculate_delta(130, 100), 30.0)
        self.assertEqual(calculate_delta(50, 100), -50.0)
        self.assertIsNone(calculate_delta(100, 0))

    @patch("app.providers.factory.ProviderFactory.get_provider")
    def test_sync_location_insights_flow(self, mock_get_provider):
        # Setup mock provider
        mock_provider = MagicMock()
        mock_get_provider.return_value = mock_provider
        
        today = datetime.date.today()
        yesterday = today - datetime.timedelta(days=1)
        
        from unittest.mock import AsyncMock
        
        from app.providers.base.models import DailyInsightMetric
        
        # 1. Mock insights from provider as a coroutine returning DailyInsightMetric
        mock_provider.get_insights = AsyncMock(return_value=[
            DailyInsightMetric(
                date=yesterday,
                search_views=150,
                map_views=50,
                phone_calls=10,
                website_clicks=20,
                direction_requests=30,
                search_queries_direct=45,
                search_queries_indirect=75,
                search_queries_chain=30
            )
        ])

        # 2. Add reviews to check merging
        review = Review(
            organization_id=self.org.id,
            location_id=self.location.id,
            provider="gbp",
            provider_review_id="review-1",
            reviewer_name="Bob Test",
            rating=5,
            comment="Awesome!",
            sentiment="positive",
            issue_category="customer-service",
            is_replied=True,
            reply_text="Thanks Bob!",
            review_created_at=datetime.datetime.combine(yesterday, datetime.time(12, 0)),
            reply_created_at=datetime.datetime.combine(yesterday, datetime.time(14, 0)) # 2 hours reply time
        )
        self.db.add(review)
        self.db.commit()

        # Run synchronization
        import asyncio
        asyncio.run(InsightSyncService.sync_location_insights(
            db=self.db,
            location_id=self.location.id,
            start_date=yesterday,
            end_date=yesterday
        ))

        # Assert data exists in DB
        insight = self.db.query(LocationDailyInsight).filter_by(
            location_id=self.location.id,
            date=yesterday
        ).first()

        self.assertIsNotNone(insight)
        self.assertEqual(insight.profile_views, 200)
        self.assertEqual(insight.reviews_received, 1)
        self.assertEqual(insight.avg_rating, 5.0)
        self.assertEqual(insight.positive_review_count, 1)
        self.assertAlmostEqual(insight.avg_response_time_hours, 2.0, places=3)
        self.assertEqual(insight.response_rate, 100.0)
        self.assertEqual(insight.click_through_rate, 10.0) # (20 / 200) * 100
        self.assertEqual(insight.call_conversion_rate, 5.0) # (10 / 200) * 100
        self.assertEqual(insight.direction_conversion_rate, 15.0) # (30 / 200) * 100
        self.assertEqual(insight.avg_sentiment_score, 1.0)

    def test_evaluate_attention_flags_triggering(self):
        today = datetime.date.today()
        # Create negative reviews and insights to trigger sentiment attention rule
        for i in range(1, 6):
            date_point = today - datetime.timedelta(days=i)
            # Create negative reviews received
            self.db.add(LocationDailyInsight(
                organization_id=self.org.id,
                location_id=self.location.id,
                date=date_point,
                provider="gbp",
                reviews_received=1,
                negative_review_count=1,
                positive_review_count=0
            ))
        self.db.commit()

        # Run attention evaluation
        InsightSyncService.evaluate_attention_flags(self.db, self.org.id)
        self.db.refresh(self.location)

        self.assertTrue(self.location.attention_needed)
        self.assertIn("Negative sentiment spike", self.location.attention_reason)

    def test_evaluate_attention_flags_no_reviews(self):
        # If there are no reviews at all in last 60 days
        InsightSyncService.evaluate_attention_flags(self.db, self.org.id)
        self.db.refresh(self.location)
        self.assertTrue(self.location.attention_needed)
        self.assertIn("No customer reviews received", self.location.attention_reason)

    @patch("app.api.deps.get_user_location_ids")
    def test_get_location_insights_security(self, mock_get_location_ids):
        # Scope user to specific locations, excluding self.location.id
        mock_get_location_ids.return_value = [99999]  # different location id
        
        with self.assertRaises(Exception) as context:
            get_location_insights(
                id=self.location.id,
                current_user=self.user,
                db=self.db
            )
        # Verify it raises HTTP 403 or 404/Scope exception
        self.assertIn("403", str(context.exception))

if __name__ == "__main__":
    unittest.main()
