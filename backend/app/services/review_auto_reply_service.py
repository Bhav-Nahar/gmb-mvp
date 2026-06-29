import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.organization import Organization
from app.models.location import Location
from app.models.review import Review
from app.models.reply_template import ReplyTemplate
from app.services.reply_template_service import ReplyTemplateService
from app.services.billing.entitlement_service import EntitlementService
from app.services.activity_log_service import ActivityLogService
from app.providers.factory import ProviderFactory

logger = logging.getLogger(__name__)

# Only positive reviews are auto-replied. Negatives always stay manual so a human
# handles them with care.
MIN_AUTO_REPLY_RATING = 4
# Oldest-first cap per run. Normal steady state is 0-2 new reviews; the cap only
# bounds the first run after a location enables the feature or a big backlog sync.
AUTO_REPLY_BATCH_LIMIT = 100
# Stop retrying a review after this many failed posts (e.g. deleted on Google),
# so failures can't permanently occupy the batch window.
MAX_AUTO_REPLY_ATTEMPTS = 5


class ReviewAutoReplyService:
    """Orchestrates auto-replying to positive reviews from reply templates.

    Kept out of the Celery task so the gate / template-pick / write-back logic is
    unit-testable without Celery, locks, or beat scheduling. The task is a thin
    entry point that owns the Redis lock and calls run().
    """

    def __init__(self, db: Session):
        self.db = db
        self._providers: dict = {}

    async def run(self, organization_id: int, location_id: int) -> dict:
        org = self.db.query(Organization).filter(Organization.id == organization_id).first()
        if not org or EntitlementService.is_org_locked(org):
            return {"status": "skipped", "reason": "org locked or missing"}
        if org.auto_reply_enabled_at is None:
            return {"status": "skipped", "reason": "auto-reply disabled"}

        location = self.db.query(Location).filter(
            Location.id == location_id,
            Location.organization_id == organization_id,
        ).first()
        if not location:
            return {"status": "skipped", "reason": "location not found"}
        if location.billing_status != "active":
            return {"status": "skipped", "reason": "location not active"}

        targets = self._find_targets(location, org.auto_reply_enabled_at)
        if not targets:
            return {"status": "skipped", "reason": "no eligible reviews"}

        replied = failed = no_template = 0
        for review in targets:
            outcome = await self._reply_one(review, location)
            if outcome == "replied":
                replied += 1
            elif outcome == "no_template":
                no_template += 1
            else:
                failed += 1

        return {
            "status": "completed",
            "replied": replied,
            "failed": failed,
            "no_template": no_template,
        }

    def _find_targets(self, location: Location, enabled_at) -> list:
        return self.db.query(Review).filter(
            Review.location_id == location.id,
            Review.organization_id == location.organization_id,
            Review.is_deleted == False,  # noqa: E712
            Review.is_replied == False,  # noqa: E712
            Review.rating >= MIN_AUTO_REPLY_RATING,
            Review.review_created_at > enabled_at,
            Review.auto_reply_attempts < MAX_AUTO_REPLY_ATTEMPTS,
        ).order_by(Review.review_created_at.asc()).limit(AUTO_REPLY_BATCH_LIMIT).all()

    def _get_provider(self, provider_name: str, organization_id: int):
        if provider_name not in self._providers:
            self._providers[provider_name] = ProviderFactory.get_provider(
                provider_name, organization_id, self.db
            )
        return self._providers[provider_name]

    async def _reply_one(self, review: Review, location: Location) -> str:
        template = ReplyTemplateService.pick_least_used(
            self.db, location.organization_id, review.rating
        )
        if template is None:
            return "no_template"

        text = ReplyTemplateService.resolve_variables(
            template.body, review.reviewer_name, location.location_name, rating=review.rating,
            city=location.city, phone=location.phone, website=location.website,
        )

        try:
            provider = self._get_provider(review.provider, location.organization_id)
            await provider.reply_review(review.provider_review_id, text)
        except Exception as e:
            # Leave is_replied=False so it retries next sync; bump the attempt counter
            # so a permanently-failing review eventually drops out of the window.
            logger.error("Auto-reply failed for review %s: %s", review.id, e, exc_info=True)
            self.db.query(Review).filter(Review.id == review.id).update(
                {Review.auto_reply_attempts: Review.auto_reply_attempts + 1},
                synchronize_session=False,
            )
            self.db.commit()
            return "failed"

        # Success write-back — mirrors the manual reply endpoint (reviews.py).
        now = datetime.now(timezone.utc)
        if review.reply_created_at is None:
            review.reply_created_at = now
        review.is_replied = True
        review.reply_text = text
        review.reply_template_id = template.id
        review.review_updated_at = now

        # Atomic increment — avoids the read-modify-write race across workers.
        self.db.query(ReplyTemplate).filter(ReplyTemplate.id == template.id).update(
            {ReplyTemplate.usage_count: ReplyTemplate.usage_count + 1},
            synchronize_session=False,
        )

        try:
            ActivityLogService.log(
                self.db,
                organization_id=location.organization_id,
                location_id=location.id,
                entity_type="review",
                entity_id=review.id,
                action="review_auto_replied",
                payload={
                    "template_id": template.id,
                    "template_rating": review.rating,
                    "trigger": "auto",
                },
            )
        except Exception as log_exc:
            logger.error("Activity log failed for auto-reply on review %s: %s", review.id, log_exc)

        self.db.commit()
        return "replied"
