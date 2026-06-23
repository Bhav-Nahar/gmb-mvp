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

        # Geography fields drive City/State/Region comparison grouping — populate them
        # on every sync so they're never NULL (was previously only via a manual backfill).
        city = addr.get("locality")
        state = addr.get("administrativeArea")
        country = addr.get("regionCode")
        postal_code = addr.get("postalCode")

        category = None
        google_category_resource_name = None
        additional_categories: list = []
        if raw.categories:
            primary = raw.categories.get("primaryCategory")
            if primary:
                category = primary.get("displayName")
                google_category_resource_name = primary.get("name")
            # GBP returns secondary categories as additionalCategories[{name, displayName}].
            # We keep both the resource name (for publishing) and displayName (for the UI).
            for c in raw.categories.get("additionalCategories") or []:
                additional_categories.append({
                    "name": c.get("name"),
                    "displayName": c.get("displayName"),
                })

        phone = None
        additional_phones: list = []
        if raw.phoneNumbers:
            phone = raw.phoneNumbers.get("primaryPhone")
            additional_phones = [p for p in (raw.phoneNumbers.get("additionalPhones") or []) if p]

        labels = list(raw.labels) if raw.labels else []

        # Capture the complete GBP payload verbatim. extra="allow" keeps any field
        # we haven't modelled; we drop the two internally-injected metrics so gbp_raw
        # reflects only what Google actually returned for the location resource.
        gbp_raw = raw.model_dump(exclude_none=True)
        gbp_raw.pop("rating", None)
        gbp_raw.pop("reviewCount", None)

        is_verified = None
        is_suspended = None
        is_duplicate = None
        
        metadata = raw.metadata or {}
        location_state = metadata.get("locationState") or raw.locationState
        if location_state:
            is_verified = location_state.get("isVerified")
            is_suspended = location_state.get("isSuspended")
            is_duplicate = location_state.get("isDuplicate")

        return LocationModel(
            provider_location_id=raw.name,
            google_account_id=account_name,
            name=raw.title or "Unnamed Location",
            category=category,
            address=full_address,
            city=city,
            state=state,
            country=country,
            postal_code=postal_code,
            phone=phone,
            website=raw.websiteUri,
            description=raw.profile.get("description") if raw.profile else None,
            business_hours=raw.regularHours.get("periods") if raw.regularHours else None,
            provider="gbp",
            provider_metadata=raw.metadata or {},
            synced_at=datetime.now(timezone.utc),
            average_rating=raw.rating,
            total_reviews=raw.reviewCount,
            google_category_resource_name=google_category_resource_name,
            additional_categories=additional_categories,
            additional_phones=additional_phones,
            special_hours=raw.specialHours,
            more_hours=raw.moreHours,
            service_area=raw.serviceArea,
            service_items=raw.serviceItems,
            labels=labels,
            open_info=raw.openInfo,
            latlng=raw.latlng,
            store_code=raw.storeCode,
            language_code=raw.languageCode,
            gbp_raw=gbp_raw,
            is_verified=is_verified,
            is_suspended=is_suspended,
            is_duplicate=is_duplicate
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
