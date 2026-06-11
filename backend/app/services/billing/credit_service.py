from contextlib import contextmanager
from typing import Generator
from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.models.organization import Organization
from app.core.plan_config import PLATFORM_AI_ACTIONS


class CreditService:
    """AI credit consumption.

    We pre-check that the org can afford the action (fail fast on locked / no
    credits) and only deduct AFTER the LLM call succeeds. The user is never
    charged for a failed generation, and there is no refund path to get wrong.
    The trade-off is that two highly-concurrent requests with one credit left
    could both pass the pre-check — acceptable for our volume."""

    @staticmethod
    @contextmanager
    def consume_ai_credit(
        db: Session, org_id: int, action_name: str, credits_required: int = 1
    ) -> Generator[None, None, None]:
        if action_name in PLATFORM_AI_ACTIONS:
            yield
            return

        from app.services.billing.entitlement_service import EntitlementService

        org = db.query(Organization).filter(Organization.id == org_id).first()
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")
        if EntitlementService.is_org_locked(org):
            raise HTTPException(status_code=402, detail="Organization is locked. Please update your subscription.")
        if (org.monthly_ai_credits_balance + org.topup_ai_credits_balance) < credits_required:
            raise HTTPException(status_code=402, detail="Insufficient AI credits")

        # Run the LLM call; if it raises, we never reach the deduction below.
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
