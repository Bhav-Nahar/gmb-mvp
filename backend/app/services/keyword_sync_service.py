import datetime
import logging
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert
from app.models.location import Location
from app.models.keyword_monthly_metrics import KeywordMonthlyMetric
from app.providers.factory import ProviderFactory

logger = logging.getLogger(__name__)

class KeywordSyncService:
    @staticmethod
    async def sync_location_keywords(db: Session, location_id: int, start_date: datetime.date, end_date: datetime.date, run_type: str = "Scheduled") -> str:
        """
        Synchronize monthly search keyword impressions for a location across a date range.
        Performs an idempotent bulk UPSERT.
        """
        location = db.query(Location).filter(Location.id == location_id).first()
        if not location:
            raise Exception(f"Location with ID {location_id} not found.")

        organization_id = location.organization_id

        # Resolve Provider and Fetch Keyword Insights
        provider_name = "gbp"
        provider = ProviderFactory.get_provider(provider_name, organization_id, db)
        provider_insights = await provider.get_search_keyword_insights(
            location_id=location.google_location_id,
            start_date=start_date,
            end_date=end_date,
            account_id=location.google_account_id
        )
        
        insert_values = []
        for insight in provider_insights:
            insert_values.append({
                "location_id": location_id,
                "google_location_id": location.google_location_id,
                "period_start": insight.period_start,
                "keyword": insight.keyword,
                "impressions": insight.impressions
            })

        # Perform idempotent bulk upsert
        if insert_values:
            stmt = insert(KeywordMonthlyMetric).values(insert_values)
            stmt = stmt.on_conflict_do_update(
                index_elements=["location_id", "period_start", "keyword"],
                set_={
                    "impressions": stmt.excluded.impressions
                }
            )
            db.execute(stmt)

        db.commit()
        return f"Successfully synchronized keyword insights for location {location_id}."
