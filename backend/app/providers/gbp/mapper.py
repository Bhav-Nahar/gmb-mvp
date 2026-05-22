from datetime import datetime
from app.providers.base.models import LocationModel, ReviewModel
from .schemas import GBPLocationRaw, GBPReviewRaw

class GBPLocationMapper:
    @staticmethod
    def to_model(raw: GBPLocationRaw) -> LocationModel:
        addr = raw.storefrontAddress or {}
        lines = addr.get("addressLines", [])
        locality = addr.get("locality", "")
        region = addr.get("administrativeArea", "")
        full_address = ", ".join(lines + [locality, region]).strip(", ")
        
        category = None
        if raw.categories and "primaryCategory" in raw.categories:
            category = raw.categories["primaryCategory"].get("displayName")
            
        phone = None
        if raw.phoneNumbers and "primaryPhone" in raw.phoneNumbers:
            phone = raw.phoneNumbers["primaryPhone"]
            
        return LocationModel(
            provider_location_id=raw.name,
            name=raw.title or "Unnamed Location",
            category=category,
            address=full_address,
            phone=phone,
            website=raw.websiteUri,
            provider="gbp",
            provider_metadata=raw.metadata or {},
            synced_at=datetime.utcnow(),
            average_rating=raw.rating,
            total_reviews=raw.reviewCount
        )

class GBPReviewMapper:
    @staticmethod
    def to_model(raw: GBPReviewRaw, location_id: str) -> ReviewModel:
        create_time = None
        if raw.createTime:
            # Google returns RFC3339, e.g., 2014-10-02T15:01:23.045123456Z
            try:
                # Basic parse (might need more robust RFC3339 parsing)
                clean_time = raw.createTime.split('.')[0] + "Z" if '.' in raw.createTime else raw.createTime
                create_time = datetime.strptime(clean_time, "%Y-%m-%dT%H:%M:%SZ")
            except Exception:
                pass
                
        update_time = None
        if raw.updateTime:
            try:
                clean_time = raw.updateTime.split('.')[0] + "Z" if '.' in raw.updateTime else raw.updateTime
                update_time = datetime.strptime(clean_time, "%Y-%m-%dT%H:%M:%SZ")
            except Exception:
                pass

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
        if raw.reviewReply and "comment" in raw.reviewReply:
            reply = raw.reviewReply["comment"]
            
        return ReviewModel(
            id=raw.reviewId,
            location_id=location_id,
            reviewer_name=reviewer_name,
            reviewer_profile_photo=reviewer_profile_photo,
            rating=rating,
            body=raw.comment,
            reply=reply,
            created_at=create_time,
            updated_at=update_time,
            provider="gbp",
            provider_metadata=raw.model_dump()
        )
