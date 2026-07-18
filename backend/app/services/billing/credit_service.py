from contextlib import contextmanager
from typing import Generator
from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.models.organization import Organization
from app.core.config import settings
from app.core.plan_config import PLATFORM_AI_ACTIONS


class CreditService:
    """AI credit consumption.

    We pre-check that the org can afford the action (fail fast on locked / no
    credits) and only deduct AFTER the work succeeds. The user is never charged
    for a failed action, and there is no refund path to get wrong. The trade-off
    is that two highly-concurrent requests with one credit left could both pass
    the pre-check — acceptable for our volume."""

    @staticmethod
    def precheck(db: Session, org_id: int, credits_required: int = 1) -> None:
        """Raise 402/404 if the org cannot afford the action. Use this to gate work
        that is deducted later (e.g. a background scan), where the consume context
        manager can't wrap the actual work."""
        from app.services.billing.entitlement_service import EntitlementService

        org = db.query(Organization).filter(Organization.id == org_id).first()
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")
        if EntitlementService.is_org_locked(org):
            raise HTTPException(status_code=402, detail="Organization is locked. Please update your subscription.")
        # Card-required onboarding: no AI spend before the trial is started, so a
        # pre-payment org can't burn credits (rank scans, replies, posts, AEO).
        if settings.CARD_REQUIRED_ONBOARDING and EntitlementService.is_onboarding(org):
            raise HTTPException(status_code=402, detail="trial_required: start your free trial to use AI features.")
        if (org.monthly_ai_credits_balance + org.topup_ai_credits_balance) < credits_required:
            raise HTTPException(status_code=402, detail="Insufficient AI credits")

    @staticmethod
    def reserve(db: Session, org_id: int, credits_required: int = 1) -> None:
        """Atomically check-and-deduct BEFORE doing expensive work.

        `precheck` reads the balance unlocked and the deduction happens after the work,
        so concurrent requests can each pass the check and run the work while only the
        affordable subset is ever charged — fine for cheap actions, but a real-money leak
        for the geo-grid scan (N² paid API calls). This does the check and the debit
        together under the org row lock, so only callers that can afford it proceed. Pair
        with refund() to return the credits if the reserved work then fails. Raises 402
        when locked or short on credits."""
        from app.services.billing.entitlement_service import EntitlementService

        stmt = select(Organization).where(Organization.id == org_id).with_for_update()
        org = db.scalars(stmt).first()
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")
        if EntitlementService.is_org_locked(org):
            raise HTTPException(status_code=402, detail="Organization is locked. Please update your subscription.")
        # Card-required onboarding: no AI spend before the trial is started, so a
        # pre-payment org can't burn credits (rank scans, replies, posts, AEO).
        if settings.CARD_REQUIRED_ONBOARDING and EntitlementService.is_onboarding(org):
            raise HTTPException(status_code=402, detail="trial_required: start your free trial to use AI features.")
        if (org.monthly_ai_credits_balance + org.topup_ai_credits_balance) < credits_required:
            raise HTTPException(status_code=402, detail="Insufficient AI credits")
        from_monthly = min(org.monthly_ai_credits_balance, credits_required)
        org.monthly_ai_credits_balance -= from_monthly
        remaining = credits_required - from_monthly
        if remaining > 0:
            org.topup_ai_credits_balance = max(0, org.topup_ai_credits_balance - remaining)
        db.commit()

    @staticmethod
    def refund(db: Session, org_id: int, credits: int) -> None:
        """Return credits reserved by reserve() when the work fails, so a failed action
        is never charged. Refunds to the monthly bucket (a small bucket imbalance vs the
        original split is acceptable for the 1–6 credit scans this guards)."""
        if credits <= 0:
            return
        stmt = select(Organization).where(Organization.id == org_id).with_for_update()
        org = db.scalars(stmt).first()
        if not org:
            return
        org.monthly_ai_credits_balance = (org.monthly_ai_credits_balance or 0) + credits
        db.commit()

    @staticmethod
    @contextmanager
    def consume_ai_credit(
        db: Session, org_id: int, action_name: str, credits_required: int = 1
    ) -> Generator[None, None, None]:
        if action_name in PLATFORM_AI_ACTIONS:
            yield
            return

        CreditService.precheck(db, org_id, credits_required)

        # Run the work; if it raises, we never reach the deduction below.
        yield

        # Deduct after success: monthly balance first, then top-up.
        stmt = select(Organization).where(Organization.id == org_id).with_for_update()
        org = db.scalars(stmt).first()
        if not org:
            return
        from_monthly = min(org.monthly_ai_credits_balance, credits_required)
        org.monthly_ai_credits_balance -= from_monthly
        remaining = credits_required - from_monthly
        if remaining > 0:
            org.topup_ai_credits_balance = max(0, org.topup_ai_credits_balance - remaining)
        db.commit()
