import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from app.models.organization import Organization
from app.core.config import settings
from app.core.redis_client import get_redis

logger = logging.getLogger(__name__)


class EntitlementService:
    """Service to handle organization locks and trial/subscription lifecycle transitions."""

    @staticmethod
    def is_onboarding(org: Organization) -> bool:
        """Pre-payment onboarding (card-required flow): Google is connected and the
        cheap audit has synced, but no payment method exists yet, so the trial clock
        has not started. Modelled as status 'trial' with trial_ends_at still NULL.

        In this state the org is deliberately NOT org-locked — the audit sync must be
        allowed to run so we can discover the location count and price the mandate —
        but premium features stay locked (see is_premium_unlocked) until a mandate
        starts the trial. NOTE: in the legacy frictionless flow the trial clock starts
        on first sync, so an org only sits here briefly before its first sync; this
        state only becomes user-visible when CARD_REQUIRED_ONBOARDING is on."""
        return org.subscription_status == "trial" and org.trial_ends_at is None

    @staticmethod
    def is_premium_unlocked(org: Organization) -> bool:
        """Whether the org may use premium / AI / analytics features.

        Stricter than `not is_org_locked`: an onboarding org (pre-payment) is unlocked
        for the audit sync yet must NOT see premium insights until it starts its trial.
        True for a running trial, an active subscription, or a past-due org still inside
        its grace window; False while onboarding or locked."""
        return (not EntitlementService.is_org_locked(org)
                and not EntitlementService.is_onboarding(org))

    @staticmethod
    def is_org_locked(org: Organization) -> bool:
        """
        Check if an organization is locked from writing or using AI/platform features.
        """
        now = datetime.now(timezone.utc)

        if org.subscription_status == "locked":
            return True

        if org.subscription_status == "past_due":
            # Locked once the grace period elapses.
            if org.grace_period_ends_at and org.grace_period_ends_at > now:
                return False
            return True

        if org.subscription_status == "trial":
            # trial_ends_at NULL = not yet activated (pending first sync). Normally not
            # locked — but cap it so an org that never connects Google can't sit in an
            # unexpiring trial forever.
            if org.trial_ends_at is None:
                from app.core.plan_config import PENDING_TRIAL_MAX_DAYS
                created = org.created_at
                if created is not None and created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)  # naive rows (SQLite tests)
                if created and created < now - timedelta(days=PENDING_TRIAL_MAX_DAYS):
                    return True
                return False
            if org.trial_ends_at < now:
                return True  # Should have been transitioned; treat as locked if past.
            return False

        # Active. A set subscription_ends_at in the past means a cancelled
        # subscription whose paid period has elapsed.
        if org.subscription_status == "active":
            if org.subscription_ends_at and org.subscription_ends_at < now:
                return True
            return False

        return False

    @staticmethod
    def transition_expired_subscriptions(db: Session) -> None:
        """
        Scan and transition expired trials and subscriptions.

        A Redis lock keeps one worker on this at a time. NOTE: in the card-required flow
        this sweep now makes one Razorpay API call per stuck/expiring card-trial, so a
        large batch could outrun the lock lease; the per-org re-lock-and-re-verify before
        any downgrade below is what actually keeps a concurrent run from mis-transitioning
        a just-activated payer. The generous lease reduces the chance of overlap.
        """
        redis_client = get_redis()
        lock = redis_client.lock("lock:transition_expired_subscriptions", timeout=900)
        
        if not lock.acquire(blocking=False):
            return  # Another worker is already processing this

        try:
            now = datetime.now(timezone.utc)

            # Step -1 (card-required flow): onboarding orgs whose mandate is authenticated
            # but whose trial never started — BOTH the /confirm fast path and the
            # subscription.authenticated webhook were missed. Without this they'd sit
            # blurred until the day-7 charge activated (and billed) them with no trial.
            # activate_trial_from_subscription is idempotent and no-ops if not yet approved.
            if settings.CARD_REQUIRED_ONBOARDING:
                from app.services.billing.subscription_service import SubscriptionService
                stuck = db.query(Organization).filter(
                    Organization.subscription_status == "trial",
                    Organization.trial_ends_at.is_(None),
                    Organization.razorpay_subscription_id.isnot(None),
                ).all()
                for org in stuck:
                    try:
                        SubscriptionService.activate_trial_from_subscription(db, org.id)
                    except Exception:
                        logger.exception("Failed to activate stuck onboarding trial for org %s", org.id)

            # Step 0: Stale PENDING trials (clock never started because the org never
            # completed a first sync) past the signup cap -> locked, so an abandoned
            # signup can't stay an unexpiring trial forever.
            from app.core.plan_config import PENDING_TRIAL_MAX_DAYS
            stale_pending = db.query(Organization).filter(
                Organization.subscription_status == "trial",
                Organization.trial_ends_at.is_(None),
                Organization.created_at < now - timedelta(days=PENDING_TRIAL_MAX_DAYS),
            ).all()
            for org in stale_pending:
                org.subscription_status = "locked"

            # Step 1: Trial -> Past Due (Grace Period). Pending trials
            # (trial_ends_at NULL) are skipped — their clock hasn't started.
            trials_to_past_due = db.query(Organization).filter(
                Organization.subscription_status == "trial",
                Organization.trial_ends_at.isnot(None),
                Organization.trial_ends_at < now
            ).all()

            for org in trials_to_past_due:
                # SAFEGUARD: a trial's first charge may have SUCCEEDED while its
                # subscription.charged webhook was missed. If the org still carries a
                # mandate, reconcile from Razorpay before locking — so a missed webhook
                # can never push a paying customer into past_due. A halted/cancelled
                # mandate reconciles to False and falls through to lock.
                # This used to be gated on CARD_REQUIRED_ONBOARDING, which meant that with
                # the flag off a subscriber whose webhook never arrived got locked without
                # anyone asking Razorpay whether they had paid. Whether the card was taken
                # up front has no bearing on "did this charge land?", so the check is
                # unconditional: the only precondition is that a mandate exists.
                # ponytail: one Razorpay fetch per expiring trial; fine at nightly volume,
                # revisit if trial expiries ever batch into the thousands.
                if org.razorpay_subscription_id:
                    from app.services.billing.subscription_service import SubscriptionService
                    try:
                        if SubscriptionService.reconcile_subscription(db, org.id):
                            continue  # first charge landed — org is now active
                    except Exception:
                        # A Razorpay outage must not abort the whole sweep. Skip locking
                        # THIS org this run (fail-open — a payer isn't wrongly locked);
                        # the next sweep retries.
                        logger.exception("Reconcile failed for expiring trial org %s; deferring.", org.id)
                        continue
                # Re-lock and re-verify before transitioning. `org` was read without a lock,
                # and reconcile / a concurrent sweep / a subscription.charged webhook may have
                # activated it since. Re-select with the SAME expired-trial predicate under a
                # row lock: if it's no longer an expired trial (e.g. just activated), the row
                # won't match and we skip it — this is what prevents a concurrent run from
                # clobbering a just-activated payer to past_due. (Predicate in SQL, not Python,
                # so the timestamp comparison is DB-consistent.)
                locked = (
                    db.query(Organization)
                    .filter(
                        Organization.id == org.id,
                        Organization.subscription_status == "trial",
                        Organization.trial_ends_at.isnot(None),
                        Organization.trial_ends_at < now,
                    )
                    .with_for_update()
                    .first()
                )
                if locked:
                    locked.subscription_status = "past_due"
                    locked.grace_period_ends_at = now + timedelta(days=3)

            # Step 2: Past Due -> Locked
            past_due_to_locked = db.query(Organization).filter(
                Organization.subscription_status == "past_due",
                Organization.grace_period_ends_at < now
            ).all()

            for org in past_due_to_locked:
                org.subscription_status = "locked"

            # Step 3: Cancelled subscription whose paid period has elapsed -> Locked.
            # A cancelled-but-still-valid sub is "active" with subscription_ends_at set.
            cancelled_to_locked = db.query(Organization).filter(
                Organization.subscription_status == "active",
                Organization.subscription_ends_at.isnot(None),
                Organization.subscription_ends_at < now
            ).all()

            for org in cancelled_to_locked:
                org.subscription_status = "locked"

            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            # If the lease expired mid-run another worker may now own the lock; releasing
            # it then raises LockNotOwnedError. Swallow it (matches the Celery task pattern)
            # so it can't mask the real outcome after a successful commit.
            try:
                lock.release()
            except Exception:
                pass
