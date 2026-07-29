import logging
import random
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.organization import Organization
from app.models.location import Location
from app.models.review import Review
from app.models.reply_template import ReplyTemplate
from app.models.activity_log import ActivityLog
from app.services.reply_template_service import ReplyTemplateService
from app.services.billing.entitlement_service import EntitlementService
from app.services.billing.credit_service import CreditService
from app.services.activity_log_service import ActivityLogService
from app.llm.exceptions import LLMProviderError
from app.providers.factory import ProviderFactory

logger = logging.getLogger(__name__)

# Template mode: 4-5★ only, since templates are written as positive replies.
MIN_AUTO_REPLY_RATING = 4
# AI mode also takes 3★, where the prompt has its own balanced/acknowledging tone.
# 1-2★ stay manual in both modes: an auto-posted apology to an angry customer is the
# one that goes wrong in public.
MIN_AI_AUTO_REPLY_RATING = 3
# Oldest-first cap per run. Normal steady state is 0-2 new reviews; the cap only
# bounds the first run after a location enables the feature or a big backlog sync.
AUTO_REPLY_BATCH_LIMIT = 100
# Stop retrying a review after this many failed posts (e.g. deleted on Google),
# so failures can't permanently occupy the batch window.
MAX_AUTO_REPLY_ATTEMPTS = 5
# AI mode only: replies per location per UTC day, so a backlog is worked through at a
# human-looking pace instead of in one burst. The exact number is re-rolled daily.
AI_DAILY_MIN, AI_DAILY_MAX = 10, 20
# Backlog replies are paced across local business hours (9am-9pm IST) instead of the
# whole UTC day, so nothing posts at 3am local. Fresh reviews are still answered on the
# sync that finds them, whatever the hour — speed is the point there.
IST_OFFSET_MIN = 330
DRIP_START_MIN, DRIP_END_MIN = 9 * 60, 21 * 60


class ReviewAutoReplyService:
    """Orchestrates auto-replying to positive reviews from reply templates.

    Kept out of the Celery task so the gate / template-pick / write-back logic is
    unit-testable without Celery, locks, or beat scheduling. The task is a thin
    entry point that owns the Redis lock and calls run().
    """

    def __init__(self, db: Session):
        self.db = db
        self._providers: dict = {}

    async def run(self, organization_id: int, location_id: int, backlog: bool = False) -> dict:
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
        if not location.auto_reply_enabled:
            return {"status": "skipped", "reason": "auto-reply off for this location"}

        ai_mode = org.auto_reply_mode == "ai"
        if backlog:
            if not ai_mode:
                return {"status": "skipped", "reason": "backlog drip is AI mode only"}
            targets = self._find_backlog_targets(location)
        elif ai_mode:
            targets = self._find_fresh_targets(location)
        else:
            targets = self._find_targets(location, org.auto_reply_enabled_at)
        if not targets:
            return {"status": "skipped", "reason": "no eligible reviews"}

        if ai_mode:
            # Pre-payment onboarding orgs may sync but must not spend AI credits, and
            # consume_ai_credit would 402 on every single target otherwise.
            if not EntitlementService.is_premium_unlocked(org):
                return self._log_run(location, {"status": "skipped", "reason": "AI features locked for this org"}, backlog)
            # An org at zero would otherwise generate a 402 on every run, forever.
            # Beyond that, no pre-slicing by balance: rating-only reviews (canned reply)
            # and reviews with an already-paid-for draft cost nothing, so a
            # targets[:budget] cut left affordable work on the table. reserve() debits
            # atomically per reply and the loop below stops on the first 402.
            budget = (org.monthly_ai_credits_balance or 0) + (org.topup_ai_credits_balance or 0)
            if budget <= 0:
                return self._log_run(location, {"status": "skipped", "reason": "no AI credits"}, backlog)

        replied = failed = no_template = skipped = 0
        stopped = None
        # Ratings with no template, remembered for this run only. Deliberately not
        # persisted on the review: adding the missing template must make the next sync
        # answer these, so they stay eligible — this only stops one pick_least_used
        # query per review when a whole rating has nothing to pick from.
        self._no_template_ratings: set[int] = set()
        for review in targets:
            try:
                outcome = await self._reply_one(review, location, ai_mode)
            except (HTTPException, LLMProviderError) as e:
                # Out of AI credits / org locked (402), or the LLM provider itself is
                # refusing us (a bad API key 400s on every single call). Nothing later in
                # this batch can succeed either, so stop instead of burning the whole
                # backlog on it — but BREAK, so the run still reaches _log_run below.
                #
                # LLMProviderError used to be uncaught: it escaped run() entirely, the
                # Celery task died mid-loop, and no activity row was ever written. The
                # panel showed "no runs" and a 1250 backlog while the worker logged the
                # same traceback every hour — invisible from the product, which is exactly
                # what the run log exists to prevent.
                stopped = getattr(e, "detail", None) or str(e)
                logger.warning("Auto-reply run stopped for location %s: %s", location.id, stopped)
                break
            if outcome == "replied":
                replied += 1
            elif outcome == "no_template":
                no_template += 1
            elif outcome == "needs_human":
                skipped += 1
            else:
                failed += 1

        return self._log_run(location, {
            "status": "completed",
            "replied": replied,
            "failed": failed,
            "no_template": no_template,
            "needs_human": skipped,
            "stopped": stopped,
        }, backlog)

    def _log_run(self, location: Location, result: dict, backlog: bool) -> dict:
        """Write one activity row per run that actually did (or failed to do) something,
        so the owner can see the automation working instead of guessing.

        ponytail: deliberately NOT logged for the states that repeat on every single sync
        forever — nothing eligible, location not billed, location opted out. Those are
        steady states, not events, and they would bury the rows that matter.
        """
        try:
            ActivityLogService.log(
                self.db,
                organization_id=location.organization_id,
                location_id=location.id,
                entity_type="location",
                entity_id=location.id,
                action="review_auto_reply_run",
                payload={**result, "backlog": backlog},
            )
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            logger.error("Auto-reply run log failed for location %s: %s", location.id, e)
        return result

    def _eligible(self, location: Location, min_rating: int = MIN_AUTO_REPLY_RATING):
        return self.db.query(Review).filter(
            Review.location_id == location.id,
            Review.organization_id == location.organization_id,
            Review.is_deleted == False,  # noqa: E712
            Review.is_replied == False,  # noqa: E712
            Review.rating >= min_rating,
            Review.auto_reply_attempts < MAX_AUTO_REPLY_ATTEMPTS,
        )

    def _find_targets(self, location: Location, enabled_at) -> list:
        return self._eligible(location).filter(
            Review.review_created_at > enabled_at,
        ).order_by(Review.review_created_at.asc()).limit(AUTO_REPLY_BATCH_LIMIT).all()

    def _daily_quota(self, location_id: int) -> int:
        """Today's target count for this location. Seeded on (location, date) so every
        run in the same day agrees on the number instead of re-rolling it each sync."""
        today = datetime.now(timezone.utc).date().isoformat()
        return random.Random(f"{location_id}:{today}").randint(AI_DAILY_MIN, AI_DAILY_MAX)

    def _replied_today(self, location: Location) -> int:
        start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        # ponytail: counted off the activity log (already written per auto-reply, and
        # indexed on location_id+created_at) — no new counter column or Redis key.
        return self.db.query(func.count(ActivityLog.id)).filter(
            ActivityLog.location_id == location.id,
            ActivityLog.action == "review_auto_replied",
            ActivityLog.created_at >= start,
        ).scalar() or 0

    def _find_fresh_targets(self, location: Location) -> list:
        """Reviews from the last day, answered on the sync that found them — deliberately
        not held back by the drip quota, so a genuinely new review never waits for a slot.
        Capped at AI_DAILY_MAX all the same: the first sync after enabling AI mode can
        surface a day's worth of reviews at once, and that must not become a 100-credit
        burst on one location.

        The cap is per DAY, not per run: it used to be a bare LIMIT, so a location with
        a steady stream of new reviews could post 20 on every sync of the day — far past
        the pace the drip promises, and 20 credits a sync."""
        room = AI_DAILY_MAX - self._replied_today(location)
        if room <= 0:
            return []
        return self._eligible(location, MIN_AI_AUTO_REPLY_RATING).filter(
            Review.review_created_at >= datetime.now(timezone.utc) - timedelta(days=1),
        ).order_by(Review.review_created_at.desc()).limit(room).all()

    @staticmethod
    def _due_by_now(quota: int, now: datetime) -> int:
        """How much of today's quota should already be posted at this time of day.

        Spread over local business hours, not the whole UTC day: the old version paced
        across 24h, so a third of the drip landed between midnight and 6am local — which
        is exactly what makes an automated reply look automated.
        ponytail: IST hardcoded (the whole customer base is India). If locations ever
        span timezones, read the offset off the location instead.
        """
        local = (now.hour * 60 + now.minute + IST_OFFSET_MIN) % (24 * 60)
        span = DRIP_END_MIN - DRIP_START_MIN
        progress = min(max(local - DRIP_START_MIN, 0), span) / span
        return round(quota * progress)

    def _backlog_room(self, location: Location) -> int:
        """Backlog replies allowed right now. Fresh replies already posted today count
        toward the quota, so a busy review day quietly shrinks the drip."""
        quota = self._daily_quota(location.id)
        due = min(self._due_by_now(quota, datetime.now(timezone.utc)), quota)
        return due - self._replied_today(location)

    def has_backlog(self, location: Location) -> bool:
        """Cheap EXISTS — lets the beat job skip locations with nothing left to drip
        instead of paying for a task that would return 'no eligible reviews'."""
        return self._backlog(location).first() is not None

    def _backlog(self, location: Location):
        return self._eligible(location, MIN_AI_AUTO_REPLY_RATING).filter(
            Review.review_created_at < datetime.now(timezone.utc) - timedelta(days=1),
        )

    def _find_backlog_targets(self, location: Location) -> list:
        """A random slice of the older backlog, paced so today's quota lands evenly over
        24h instead of in one burst.

        A random *window* rather than ORDER BY random(): the latter has to read and sort
        every unreplied row for the location on each of the 24 daily ticks, while this
        is an indexed count plus a walk to the offset. The window is contiguous by id,
        so we shuffle what comes back — otherwise the day's replies would post in
        review order, which reads mechanical."""
        room = self._backlog_room(location)
        if room <= 0:
            return []
        q = self._backlog(location)
        total = q.count()
        if total <= room:
            return q.all()
        rows = q.order_by(Review.id).offset(random.randint(0, total - room)).limit(room).all()
        random.shuffle(rows)
        return rows

    def _get_provider(self, provider_name: str, organization_id: int):
        if provider_name not in self._providers:
            self._providers[provider_name] = ProviderFactory.get_provider(
                provider_name, organization_id, self.db
            )
        return self._providers[provider_name]

    async def _ai_text(self, review: Review, location: Location) -> str | None:
        """One AI reply, or None if it must not be auto-posted. Raises HTTPException(402)
        when the org is out of credits (the caller stops the whole run)."""
        from app.services import reply_validation
        from app.services.ai_reply_service import generate_reply, empty_review_reply

        # A previous run generated and validated this one, then failed to post it.
        # Reuse it: the credit is already spent, and regenerating would charge again.
        if review.ai_reply_draft:
            logger.info("Reusing paid-for AI draft on review %s", review.id)
            return review.ai_reply_draft

        sensitive = reply_validation.is_sensitive_category(
            location.primary_category, location.location_name
        )
        if not (review.comment or "").strip():
            return empty_review_reply(review.rating, sensitive)  # canned, no LLM, no credit

        with CreditService.consume_ai_credit(self.db, location.organization_id,
                                             "generate_review_reply"):
            result = await generate_reply(review, location, self.db)
        text = result["variants"]["recommended"]

        check = reply_validation.validate(
            text, review.sentiment, review.rating, review.comment,
            min_words=18 if sensitive else 30, max_words=60,
            sensitive=sensitive, reviewer_name=review.reviewer_name or "",
        )
        if check["manual_review_required"] or check["violations"]:
            # Automation never posts a reply a human would have been asked to check.
            logger.info("AI auto-reply skipped review %s: %s", review.id, check["violations"])
            return None
        # Bank the paid-for text before the Google call, so a failed post (or a worker
        # dying mid-batch) costs the retry nothing.
        review.ai_reply_draft = text
        self.db.commit()
        return text

    async def _reply_one(self, review: Review, location: Location, ai_mode: bool = False) -> str:
        template = None
        if ai_mode:
            text = await self._ai_text(review, location)
            if text is None:
                # Don't retry it every sync — a flagged review needs a person, not a retry.
                self.db.query(Review).filter(Review.id == review.id).update(
                    {Review.auto_reply_attempts: MAX_AUTO_REPLY_ATTEMPTS},
                    synchronize_session=False,
                )
                self.db.commit()
                return "needs_human"
        else:
            if review.rating in getattr(self, "_no_template_ratings", set()):
                return "no_template"
            template = ReplyTemplateService.pick_least_used(
                self.db, location.organization_id, review.rating
            )
            if template is None:
                self._no_template_ratings.add(review.rating)
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
        review.reply_template_id = template.id if template else None
        review.review_updated_at = now
        review.ai_reply_draft = None  # it's live now, stop holding the draft

        if template:
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
                    "template_id": template.id if template else None,
                    "template_rating": review.rating,
                    "trigger": "auto",
                    "source": "ai" if ai_mode else "template",
                },
            )
        except Exception as log_exc:
            logger.error("Activity log failed for auto-reply on review %s: %s", review.id, log_exc)

        self.db.commit()
        return "replied"
