import datetime
import logging
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert
from app.models.location import Location
from app.models.keyword_monthly_metrics import KeywordMonthlyMetric
from app.providers.factory import ProviderFactory

logger = logging.getLogger(__name__)

# The two most recent months may still be settling on Google's side; everything
# older is final. So we always re-fetch this trailing window but skip months we
# already have stored — the GBP keyword API is billed per month.
_REFRESH_TRAILING_MONTHS = 2


def _month_starts(start: datetime.date, end: datetime.date) -> list[datetime.date]:
    """First-of-month dates from start to end, inclusive."""
    months, cur, last = [], start.replace(day=1), end.replace(day=1)
    while cur <= last:
        months.append(cur)
        cur = (cur.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
    return months


def _months_back(month_start: datetime.date, n: int) -> datetime.date:
    """The first-of-month n months before month_start."""
    for _ in range(n):
        month_start = (month_start - datetime.timedelta(days=1)).replace(day=1)
    return month_start


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

        # Skip months already stored (final data), but always refresh the trailing
        # window that may still be settling. Each month we skip is one GBP API call saved.
        month_starts = _month_starts(start_date, end_date)
        refresh_floor = _months_back(end_date.replace(day=1), _REFRESH_TRAILING_MONTHS - 1)
        existing = {
            row[0] for row in db.query(KeywordMonthlyMetric.period_start)
            .filter(
                KeywordMonthlyMetric.location_id == location_id,
                KeywordMonthlyMetric.period_start.in_(month_starts),
            ).distinct()
        }
        to_fetch = [m for m in month_starts if m not in existing or m >= refresh_floor]
        if not to_fetch:
            return f"Keyword insights already current for location {location_id}; no fetch needed."
        # Missing months are always the recent tail, so fetching min(to_fetch)->end
        # covers them (UPSERT absorbs any re-fetched month) while skipping stable history.
        fetch_start = min(to_fetch)

        # Resolve Provider and Fetch Keyword Insights
        provider_name = "gbp"
        provider = ProviderFactory.get_provider(provider_name, organization_id, db)
        provider_insights = await provider.get_search_keyword_insights(
            location_id=location.google_location_id,
            start_date=fetch_start,
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
