import json
import logging
from datetime import datetime, timezone
from typing import Optional
from app.providers.base.models import LocationModel, ReviewModel
from .schemas import GBPLocationRaw, GBPReviewRaw

logger = logging.getLogger(__name__)


def parse_gbp_datetime(raw: Optional[str]) -> Optional[datetime]:
    """Parse a GBP RFC3339 datetime string robustly, returning None on failure."""
    if not raw:
        return None
    try:
        normalized = raw.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError as e:
        logger.warning("Failed to parse GBP datetime %r: %s", raw, e)
        return None


class GBPLocationMapper:
    @staticmethod
    def to_model(raw: GBPLocationRaw, account_name: Optional[str] = None) -> LocationModel:
        addr = raw.storefrontAddress or {}
        full_address = None
        if addr:
            try:
                full_address = json.dumps(addr, default=str)
            except Exception as e:
                logger.warning("Failed to JSON-serialize address %r: %s", addr, e)

        category = None
        google_category_resource_name = None
        if raw.categories and "primaryCategory" in raw.categories:
            category = raw.categories["primaryCategory"].get("displayName")
            google_category_resource_name = raw.categories["primaryCategory"].get("name")

        phone = None
        if raw.phoneNumbers and "primaryPhone" in raw.phoneNumbers:
            phone = raw.phoneNumbers["primaryPhone"]

        return LocationModel(
            provider_location_id=raw.name,
            google_account_id=account_name,
            name=raw.title or "Unnamed Location",
            category=category,
            address=full_address,
            phone=phone,
            website=raw.websiteUri,
            description=raw.profile.get("description") if raw.profile else None,
            business_hours=raw.regularHours.get("periods") if raw.regularHours else None,
            provider="gbp",
            provider_metadata=raw.metadata or {},
            synced_at=datetime.now(timezone.utc),
            average_rating=raw.rating,
            total_reviews=raw.reviewCount,
            google_category_resource_name=google_category_resource_name
        )


class GBPReviewMapper:
    @staticmethod
    def to_model(raw: GBPReviewRaw, location_id: str) -> ReviewModel:
        create_time = parse_gbp_datetime(raw.createTime)
        update_time = parse_gbp_datetime(raw.updateTime)

        reviewer_name = "Anonymous"
        if raw.reviewer and "displayName" in raw.reviewer:
            reviewer_name = raw.reviewer["displayName"]

        reviewer_profile_photo = None
        if raw.reviewer and "profilePhotoUrl" in raw.reviewer:
            reviewer_profile_photo = raw.reviewer["profilePhotoUrl"]

        # starRating comes back as "ONE", "TWO", "THREE", "FOUR", "FIVE"
        star_map = {
            "FIVE": 5,
            "FOUR": 4,
            "THREE": 3,
            "TWO": 2,
            "ONE": 1,
            "STAR_RATING_UNSPECIFIED": None
        }
        rating = star_map.get(raw.starRating, None)

        reply = None
        reply_created_at = None
        if raw.reviewReply and "comment" in raw.reviewReply:
            reply = raw.reviewReply["comment"]
            reply_time_str = raw.reviewReply.get("updateTime")
            if reply_time_str:
                reply_created_at = parse_gbp_datetime(reply_time_str)

        return ReviewModel(
            id=raw.reviewId,
            location_id=location_id,
            reviewer_name=reviewer_name,
            reviewer_profile_photo=reviewer_profile_photo,
            rating=rating,
            body=raw.comment,
            reply=reply,
            reply_created_at=reply_created_at,
            created_at=create_time,
            updated_at=update_time,
            provider="gbp",
            provider_metadata=raw.model_dump()
        )
